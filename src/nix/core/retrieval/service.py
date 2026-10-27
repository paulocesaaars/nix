"""Fachada de recuperação híbrida, inclusive juntando vários vaults."""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from nix.config.schema import NixConfig, VaultSettings
from nix.core.errors import NixError
from nix.core.index.embedder import Embedder
from nix.core.index.store import IndexStore
from nix.core.index.vectorstore import VectorStore
from nix.core.models import RetrievedChunk
from nix.core.retrieval.fusion import reciprocal_rank_fusion
from nix.core.retrieval.lexical import LexicalSearch
from nix.core.retrieval.rerank import Reranker
from nix.core.retrieval.vector import VectorSearch
from nix.core.vault.paths import is_included, matches_folder
from nix.observability.logging import get_logger

logger = get_logger("nix.retrieval")


@dataclass(frozen=True)
class MultiSearchResult:
    """Trechos já cortados por score e as falhas que não derrubaram a busca."""

    chunks: list[RetrievedChunk]
    vault_errors: list[dict[str, str]]


class RetrievalService:
    def __init__(
        self,
        config: NixConfig,
        vault: VaultSettings,
        store: IndexStore,
        vectors: VectorStore,
        embedder: Embedder,
    ) -> None:
        self.config = config
        self._vault = vault
        self.store = store
        self.vector = VectorSearch(vectors, embedder)
        self.lexical = LexicalSearch(store)
        self._reranker: Reranker | None = None

    def _rerank(self) -> Reranker:
        if self._reranker is None:
            self._reranker = Reranker(self.config.index.rerank_model)
        return self._reranker

    def embed_query(self, query: str) -> list[float]:
        return self.vector.embed_query(query)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        folder: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        expand_neighbors: bool | None = None,
        use_rerank: bool | None = None,
        embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        settings = self.config.retrieval
        k = top_k or settings.top_k
        vector = embedding if embedding is not None else self.embed_query(query)
        found = self.collect(
            query,
            embedding=vector,
            top_k=k,
            folder=folder,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            expand_neighbors=expand_neighbors,
        )
        return self.finish(query, found, k=k, use_rerank=use_rerank, rerank_window=20)

    def collect(
        self,
        query: str,
        *,
        embedding: list[float],
        top_k: int,
        folder: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        expand_neighbors: bool | None = None,
    ) -> list[RetrievedChunk]:
        """Híbrida com o pool de candidatos e os filtros. Sem corte final nem rerank."""
        settings = self.config.retrieval
        pool = max(top_k, settings.candidate_pool)
        dense: list[RetrievedChunk] = []
        lexical: list[RetrievedChunk] = []

        def _dense() -> list[RetrievedChunk]:
            return self.vector.search(
                query,
                pool,
                embedding=embedding,
                folder=folder,
                tags=tags,
                date_from=date_from,
                date_to=date_to,
            )

        def _lex() -> list[RetrievedChunk]:
            return self.lexical.search(query, pool, expand=settings.expand_query)

        if settings.hybrid:
            with ThreadPoolExecutor(max_workers=2) as pool_exec:
                f_dense = pool_exec.submit(_dense)
                f_lex = pool_exec.submit(_lex)
                dense = f_dense.result()
                lexical = self._filter(f_lex.result(), folder=folder, tags=tags)
            fused = reciprocal_rank_fusion(
                [dense, lexical],
                k=settings.rrf_k,
                weights=[1.0 - settings.lexical_weight, settings.lexical_weight],
            )
        else:
            fused = _dense()

        fused = self._filter(fused, folder=folder, tags=tags)
        expand = settings.neighbor_expansion > 0 if expand_neighbors is None else expand_neighbors
        if expand:
            fused = self._expand(fused, settings.neighbor_expansion)
        return fused

    def finish(
        self,
        query: str,
        fused: list[RetrievedChunk],
        *,
        k: int,
        use_rerank: bool | None = None,
        rerank_window: int | None = 20,
    ) -> list[RetrievedChunk]:
        """Aplica rerank, top_k e o piso de score no conjunto já ordenado."""
        settings = self.config.retrieval
        do_rerank = settings.rerank if use_rerank is None else use_rerank
        if do_rerank and fused:
            window = fused if rerank_window is None else fused[:rerank_window]
            try:
                fused = self._rerank().rerank(query, window, k)
            except Exception:
                logger.warning("Reordenação falhou; usando o ranking híbrido.", exc_info=True)
                fused = fused[:k]
        else:
            fused = fused[:k]
        if not fused:
            return []
        best = fused[0].score
        floor = max(settings.min_score, best * 0.65)
        return [chunk for chunk in fused if chunk.score >= floor]

    def _filter(
        self,
        chunks: list[RetrievedChunk],
        *,
        folder: str | None,
        tags: list[str] | None,
    ) -> list[RetrievedChunk]:
        wanted = {t.lower() for t in (tags or [])}
        include = self._vault.include
        exclude = self._vault.exclude
        out: list[RetrievedChunk] = []
        for chunk in chunks:
            if not is_included(
                chunk.rel_path,
                include,
                exclude,
                apply_include=chunk.rel_path.lower().endswith(".md"),
            ):
                continue
            if not matches_folder(chunk.rel_path, folder):
                continue
            if wanted and not wanted.intersection({t.lower() for t in chunk.tags}):
                continue
            out.append(chunk)
        return out

    def _expand(self, chunks: list[RetrievedChunk], radius: int) -> list[RetrievedChunk]:
        if radius <= 0 or not chunks:
            return chunks
        seen = {c.chunk_id for c in chunks}
        extra: list[RetrievedChunk] = []
        for chunk in chunks[: max(1, len(chunks) // 2)]:
            for row in self.store.neighbor_chunks(chunk.file_id, chunk.ordinal, radius):
                cid = str(row["id"])
                if cid in seen:
                    continue
                seen.add(cid)
                rel = str(row["rel_path"])
                try:
                    tags = [str(t) for t in json.loads(row["file_tags"] or "[]")]
                except json.JSONDecodeError:
                    tags = []
                extra.append(
                    RetrievedChunk(
                        chunk_id=cid,
                        file_id=str(row["file_id"]),
                        rel_path=rel,
                        title=str(row["title"] or chunk.title),
                        heading_path=str(row["heading_path"] or ""),
                        content=str(row["content"] or ""),
                        score=chunk.score * 0.9,
                        ordinal=int(row["ordinal"] or 0),
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        tags=tags,
                        folder=rel.rsplit("/", 1)[0] if "/" in rel else "",
                        mtime=float(row["mtime"] or 0.0),
                        vault=chunk.vault,
                    )
                )
        return chunks + extra


def search_many(
    services: Sequence[tuple[str, RetrievalService]],
    query: str,
    *,
    top_k: int | None = None,
    folder: str | None = None,
    tags: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    expand_neighbors: bool | None = None,
    use_rerank: bool | None = None,
) -> MultiSearchResult:
    """Vetoriza uma vez, junta pelo score e reranqueia o conjunto, se o rerank estiver ligado.

    Falha num vault vai para `vault_errors` com a ação corretiva. Os outros seguem.
    """
    if not services:
        return MultiSearchResult(chunks=[], vault_errors=[])
    primary = services[0][1]
    settings = primary.config.retrieval
    k = top_k or settings.top_k
    embedding = primary.embed_query(query)
    merged: list[RetrievedChunk] = []
    errors: list[dict[str, str]] = []
    for name, service in services:
        try:
            found = service.collect(
                query,
                embedding=embedding,
                top_k=k,
                folder=folder,
                tags=tags,
                date_from=date_from,
                date_to=date_to,
                expand_neighbors=expand_neighbors,
            )
        except NixError as exc:
            errors.append({"vault": name, "message": exc.message})
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("Busca falhou no vault %s", name)
            errors.append(
                {
                    "vault": name,
                    "message": (
                        f"A busca no vault {name} falhou ({exc}). "
                        f"Rode `nix sync --vault {name}` e tente de novo."
                    ),
                }
            )
            continue
        merged.extend(replace(chunk, vault=name) for chunk in found)
    merged.sort(key=lambda chunk: chunk.score, reverse=True)
    chunks = primary.finish(query, merged, k=k, use_rerank=use_rerank, rerank_window=None)
    return MultiSearchResult(chunks=chunks, vault_errors=errors)
