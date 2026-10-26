"""Grafo de wikilinks derivado do estado indexado."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TypeVar

from nix.core.index.store import IndexStore
from nix.core.models import LinkDirection, NoteRef
from nix.core.vault.paths import to_posix

T = TypeVar("T")


def note_stem(rel_path: str) -> str:
    """Stem do arquivo, sem a extensão `.md`."""
    name = to_posix(rel_path).rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        return name[:-3]
    return name


def register_note_alias(aliases: dict[str, T], rel_path: str, title: str, value: T) -> None:
    """Registra título e stem. A última gravação da chave fica dona.

    A ordem é a do grafo: primeiro o título, depois o stem do arquivo.
    Entre notas com o mesmo stem, vence a última da iteração.
    """
    aliases[title.lower()] = value
    aliases[note_stem(rel_path).lower()] = value


def stem_owner(rows: Iterable[tuple[str, str]], rel_path: str) -> str | None:
    """Caminho da nota dona do stem de `rel_path`. None se ninguém indexou essa chave."""
    aliases: dict[str, str] = {}
    for rel, title in rows:
        posix = to_posix(rel)
        register_note_alias(aliases, posix, title, posix)
    return aliases.get(note_stem(rel_path).lower())


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
            register_note_alias(by_title, rel, title, ref)
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
