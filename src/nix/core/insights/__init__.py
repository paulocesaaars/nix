"""Insights sobre o vault: órfãs, duplicatas, sugestão de links e resumo."""

from __future__ import annotations

import json
from collections import defaultdict

from nix.core.index.graph import WikiGraph
from nix.core.index.store import IndexStore
from nix.core.models import InsightDuplicate, LinkSuggestion, NoteRef


class InsightsService:
    def __init__(self, store: IndexStore, graph: WikiGraph) -> None:
        self._store = store
        self._graph = graph

    def orphans(self) -> list[NoteRef]:
        self._graph.rebuild()
        linked_targets: set[str] = set()
        rows = self._store.list_files()
        for row in rows:
            if row["status"] != "indexed":
                continue
            try:
                links = json.loads(row["links"] or "[]")
            except json.JSONDecodeError:
                links = []
            for target in links:
                linked_targets.add(str(target).lower())
        orphans: list[NoteRef] = []
        for row in rows:
            if row["status"] != "indexed":
                continue
            title = str(row["title"] or "")
            rel = str(row["rel_path"])
            neighbors = self._graph.neighbors(rel, "both")
            if not neighbors and title.lower() not in linked_targets:
                orphans.append(NoteRef(rel_path=rel, title=title, tags=_tags(row["tags"])))
        return orphans

    def duplicates(self) -> list[InsightDuplicate]:
        by_title: dict[str, list[str]] = defaultdict(list)
        for row in self._store.list_files():
            if row["status"] != "indexed":
                continue
            title = str(row["title"] or "").strip()
            if title:
                by_title[title.lower()].append(str(row["rel_path"]))
        return [
            InsightDuplicate(title=key, paths=paths)
            for key, paths in sorted(by_title.items())
            if len(paths) > 1
        ]

    def suggest_links(self, limit: int = 20) -> list[LinkSuggestion]:
        self._graph.rebuild()
        titles = [
            (rel, title, body)
            for rel, title, body in self._store.indexed_bodies()
            if title
        ]
        suggestions: list[LinkSuggestion] = []
        for rel, title, body in titles:
            already = {n.rel_path for n in self._graph.neighbors(rel, "outgoing")}
            for other_rel, other_title, _other_body in titles:
                if other_rel == rel or not other_title or len(other_title) < 4:
                    continue
                if other_rel in already:
                    continue
                if other_title in body and f"[[{other_title}]]" not in body:
                    suggestions.append(
                        LinkSuggestion(
                            rel_path=rel,
                            title=title,
                            suggested_target=other_title,
                            reason=f"O texto de {rel} menciona {other_title!r} sem wikilink.",
                        )
                    )
                    if len(suggestions) >= limit:
                        return suggestions
                    break
        return suggestions

    def summary(self) -> dict[str, object]:
        files = self._store.count_markdown("indexed")
        chunks = self._store.count_chunks()
        errors = self._store.count_files("error")
        orphans = self.orphans()
        dups = self.duplicates()
        return {
            "files": files,
            "chunks": chunks,
            "errors": errors,
            "orphans": len(orphans),
            "duplicate_titles": len(dups),
            "orphan_sample": [o.rel_path for o in orphans[:10]],
        }


def _tags(raw: object) -> list[str]:
    try:
        return [str(t) for t in json.loads(str(raw) if raw is not None else "[]")]
    except json.JSONDecodeError:
        return []
