"""Fachada de recuperação híbrida."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from nix.config.schema import NixConfig
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


class RetrievalService:
    def __init__(
        self,
        config: NixConfig,
        store: IndexStore,
        vectors: VectorStore,
        embedder: Embedder,
    ) -> None:
        self.config = config
        self.store = store
        self.vector = VectorSearch(vectors, embedder)
        self.lexical = LexicalSearch(store)
        self._reranker: Reranker | None = None

    def _rerank(self) -> Reranker:
        if self._reranker is None:
            self._reranker = Reranker(self.config.index.rerank_model)
        return self._reranker

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
    ) -> list[RetrievedChunk]:
        settings = self.config.retrieval
        k = top_k or settings.top_k
        pool = max(k, settings.candidate_pool)
        dense: list[RetrievedChunk] = []
        lexical: list[RetrievedChunk] = []

        def _dense() -> list[RetrievedChunk]:
            return self.vector.search(
                query,
                pool,
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
        if expand_neighbors if expand_neighbors is not None else settings.neighbor_expansion > 0:
            fused = self._expand(fused, settings.neighbor_expansion)
        do_rerank = settings.rerank if use_rerank is None else use_rerank
        if do_rerank and fused:
            try:
                fused = self._rerank().rerank(query, fused[:20], k)
            except Exception:
                logger.warning("Reordenação falhou; usando o ranking híbrido.", exc_info=True)
                fused = fused[:k]
        else:
            fused = fused[:k]
        if not fused:
            return []
        min_score = settings.min_score
        best = fused[0].score
        floor = max(min_score, best * 0.65)
        return [c for c in fused if c.score >= floor]

    def _filter(
        self,
        chunks: list[RetrievedChunk],
        *,
        folder: str | None,
        tags: list[str] | None,
    ) -> list[RetrievedChunk]:
        wanted = {t.lower() for t in (tags or [])}
        include = self.config.vault.include
        exclude = self.config.vault.exclude
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
                    )
                )
        return chunks + extra
