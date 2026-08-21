"""Busca léxica FTS5 com sanitização da consulta."""

from __future__ import annotations

import json
import re

from nix.core.index.store import IndexStore
from nix.core.models import RetrievedChunk

_TOKEN = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def to_fts_query(query: str, *, expand: bool = True) -> str:
    tokens = _TOKEN.findall(query)
    if not tokens:
        return '""'
    quoted = ['"' + t.replace('"', "") + '"' for t in tokens[:32]]
    joiner = " OR " if expand else " AND "
    return joiner.join(quoted)


class LexicalSearch:
    def __init__(self, store: IndexStore) -> None:
        self._store = store

    def search(self, query: str, k: int, *, expand: bool = True) -> list[RetrievedChunk]:
        fts = to_fts_query(query, expand=expand)
        rows = self._store.search_fts(fts, k)
        results: list[RetrievedChunk] = []
        for row in rows:
            tags_raw = row["file_tags"]
            try:
                tags = [str(t) for t in json.loads(tags_raw or "[]")]
            except json.JSONDecodeError:
                tags = []
            rel = str(row["rel_path"])
            folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
            bm25 = float(row["rank"] or 0.0)
            score = 1.0 / (1.0 + abs(bm25))
            results.append(
                RetrievedChunk(
                    chunk_id=str(row["id"]),
                    file_id=str(row["file_id"]),
                    rel_path=rel,
                    title=str(row["title"] or ""),
                    heading_path=str(row["heading_path"] or ""),
                    content=str(row["content"] or ""),
                    score=score,
                    ordinal=int(row["ordinal"] or 0),
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    tags=tags,
                    folder=folder,
                    mtime=float(row["mtime"] or 0.0),
                )
            )
        return results
