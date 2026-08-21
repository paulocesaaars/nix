"""Adaptador ChromaDB persistente."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from nix.core.models import Chunk, RetrievedChunk
from nix.observability.logging import get_logger
from nix.observability.stdio import capture_library_stdout

logger = get_logger("nix.index.vectorstore")

COLLECTION = "nix_notes"


def _meta(chunk: Chunk) -> dict[str, Any]:
    return {
        "file_id": chunk.file_id,
        "rel_path": chunk.rel_path,
        "title": chunk.title,
        "heading_path": chunk.heading_path,
        "tags": ",".join(chunk.tags),
        "folder": chunk.folder,
        "mtime": float(chunk.mtime),
        "ordinal": int(chunk.ordinal),
        "start_line": int(chunk.start_line or 0),
        "end_line": int(chunk.end_line or 0),
    }


class VectorStore:
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client: object | None = None
        self._collection: object | None = None

    def _col(self) -> Any:
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings

            with capture_library_stdout():
                self._client = chromadb.PersistentClient(
                    path=str(self.persist_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(  # type: ignore[union-attr]
                    name=COLLECTION,
                    metadata={"hnsw:space": "cosine"},
                )
        return self._collection

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        col = self._col()
        col.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.content for c in chunks],
            metadatas=[_meta(c) for c in chunks],
        )

    def delete_file(self, file_id: str) -> None:
        try:
            self._col().delete(where={"file_id": file_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao remover vetores de file_id=%s: %s", file_id, exc)

    def query(
        self,
        embedding: list[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": max(1, k),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        raw = self._col().query(**kwargs)
        ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]
        results: list[RetrievedChunk] = []
        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists, strict=False):
            meta = meta or {}
            distance = float(dist)
            score = 1.0 / (1.0 + max(distance, 0.0))
            tags_raw = str(meta.get("tags") or "")
            results.append(
                RetrievedChunk(
                    chunk_id=str(chunk_id),
                    file_id=str(meta.get("file_id") or ""),
                    rel_path=str(meta.get("rel_path") or ""),
                    title=str(meta.get("title") or ""),
                    heading_path=str(meta.get("heading_path") or ""),
                    content=str(doc or ""),
                    score=score,
                    ordinal=int(meta.get("ordinal") or 0),
                    start_line=int(meta["start_line"]) if meta.get("start_line") else None,
                    end_line=int(meta["end_line"]) if meta.get("end_line") else None,
                    tags=[t for t in tags_raw.split(",") if t],
                    folder=str(meta.get("folder") or ""),
                    mtime=float(meta.get("mtime") or 0.0),
                )
            )
        return results

    def reset(self) -> None:
        import chromadb
        from chromadb.config import Settings

        with capture_library_stdout():
            client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            with contextlib.suppress(Exception):
                client.delete_collection(COLLECTION)
            self._client = client
            self._collection = client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
