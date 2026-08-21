"""Reordenação com cross-encoder local (FastEmbed)."""

from __future__ import annotations

from nix.core.models import RetrievedChunk
from nix.observability.logging import get_logger
from nix.observability.stdio import capture_library_stdout

logger = get_logger("nix.retrieval.rerank")


class Reranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def _ensure(self) -> object:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            logger.info("Carregando cross-encoder %s", self.model_name)
            with capture_library_stdout():
                self._model = TextCrossEncoder(model_name=self.model_name)
        return self._model

    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        model = self._ensure()
        docs = [c.content for c in chunks]
        try:
            with capture_library_stdout():
                scores = list(model.rerank(query, docs))  # type: ignore[attr-defined]
        except Exception:
            with capture_library_stdout():
                raw = list(model.rerank(query, docs))  # type: ignore[attr-defined]
            scores = [float(item[1]) if isinstance(item, tuple | list) else float(item) for item in raw]
        if len(scores) != len(chunks) and scores:
            # alguns modelos devolvem já ordenados
            pass
        paired = list(zip(chunks, [float(s) for s in scores], strict=False))
        paired.sort(key=lambda item: item[1], reverse=True)
        out: list[RetrievedChunk] = []
        for chunk, score in paired[:top_k]:
            out.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    file_id=chunk.file_id,
                    rel_path=chunk.rel_path,
                    title=chunk.title,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    score=score,
                    ordinal=chunk.ordinal,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    tags=chunk.tags,
                    folder=chunk.folder,
                    mtime=chunk.mtime,
                )
            )
        return out
