"""Grafo de wikilinks derivado do estado indexado."""

from __future__ import annotations

from collections import defaultdict

from nix.core.index.store import IndexStore
from nix.core.models import LinkDirection, NoteRef


class WikiGraph:
    def __init__(self, store: IndexStore) -> None:
        self._store = store
        self._cache: tuple[
            dict[str, NoteRef],
            dict[str, NoteRef],
            dict[str, list[str]],
            dict[str, list[str]],
        ] | None = None

    def invalidate(self) -> None:
        self._cache = None

    def rebuild(self) -> None:
        self._cache = self._indexes()

    def _cached(
        self,
    ) -> tuple[dict[str, NoteRef], dict[str, NoteRef], dict[str, list[str]], dict[str, list[str]]]:
        if self._cache is None:
            self.rebuild()
        assert self._cache is not None
        return self._cache

    def _indexes(
        self,
    ) -> tuple[dict[str, NoteRef], dict[str, NoteRef], dict[str, list[str]], dict[str, list[str]]]:
        by_title: dict[str, NoteRef] = {}
        by_path: dict[str, NoteRef] = {}
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)
        for rel, title, links, tags in self._store.all_indexed_links():
            ref = NoteRef(rel_path=rel, title=title, tags=tags)
            by_path[rel] = ref
            by_title[title.lower()] = ref
            stem = rel.rsplit("/", 1)[-1]
            if stem.lower().endswith(".md"):
                stem = stem[:-3]
            by_title[stem.lower()] = ref
            for target in links:
                outgoing[rel].append(target)
        for rel, targets in outgoing.items():
            for target in targets:
                dest = by_title.get(target.lower())
                if dest:
                    incoming[dest.rel_path].append(rel)
        return by_path, by_title, outgoing, incoming

    def neighbors(self, rel_path: str, direction: LinkDirection = "both") -> list[NoteRef]:
        by_path, by_title, outgoing, incoming = self._cached()
        if rel_path not in by_path and self._store.get_file(rel_path) is None:
            return []
        found: dict[str, NoteRef] = {}
        if direction in ("outgoing", "both"):
            for target in outgoing.get(rel_path, []):
                dest = by_title.get(target.lower())
                if dest:
                    found[dest.rel_path] = dest
                    continue
                stem = target if target.endswith(".md") else f"{target}.md"
                dest = by_path.get(stem) or by_path.get(target)
                if dest:
                    found[dest.rel_path] = dest
        if direction in ("incoming", "both"):
            for src_path in incoming.get(rel_path, []):
                dest = by_path.get(src_path)
                if dest:
                    found[src_path] = dest
        found.pop(rel_path, None)
        return list(found.values())
