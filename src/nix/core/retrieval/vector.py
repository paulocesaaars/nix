"""Busca densa no Chroma, com filtros por pasta/tag/data aplicados depois quando preciso."""

from __future__ import annotations

from datetime import UTC, datetime

from nix.core.index.embedder import Embedder
from nix.core.index.vectorstore import VectorStore
from nix.core.models import RetrievedChunk
from nix.core.vault.paths import matches_folder


def _parse_date(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(text.replace("Z", ""), fmt.replace("Z", ""))
            return dt.replace(tzinfo=UTC).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class VectorSearch:
    def __init__(self, vectors: VectorStore, embedder: Embedder) -> None:
        self._vectors = vectors
        self._embedder = embedder

    def search(
        self,
        query: str,
        k: int,
        *,
        folder: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[RetrievedChunk]:
        embedding = self._embedder.embed_query(query)
        extra = bool(folder or tags or date_from or date_to)
        pool = max(k, k * 4 if extra else k)
        hits = self._vectors.query(embedding, pool, where=None)
        start = _parse_date(date_from)
        end = _parse_date(date_to)
        wanted = {t.lower() for t in (tags or [])}
        filtered: list[RetrievedChunk] = []
        for hit in hits:
            if not matches_folder(hit.rel_path, folder):
                continue
            if wanted and not wanted.intersection({t.lower() for t in hit.tags}):
                continue
            if start is not None and hit.mtime < start:
                continue
            if end is not None and hit.mtime > end + 86400:
                continue
            filtered.append(hit)
        return filtered[:k]
