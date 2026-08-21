"""Ferramentas de busca e leitura de notas."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from nix.core.errors import NoteNotFoundError, VaultError
from nix.core.models import LinkDirection, NoteContent, NoteRef
from nix.core.runtime import Runtime
from nix.core.vault.paths import assert_accessible, is_included


class SearchNotesArgs(BaseModel):
    query: str = Field(description="Consulta em linguagem natural ou termos-chave")
    top_k: int = Field(default=5, ge=1, le=50)
    folder: str | None = Field(default=None, description="Pasta relativa ao vault")
    tags: list[str] | None = Field(default=None)
    date_from: str | None = Field(default=None, description="ISO YYYY-MM-DD")
    date_to: str | None = Field(default=None, description="ISO YYYY-MM-DD")


class ReadNoteArgs(BaseModel):
    rel_path: str = Field(description="Caminho relativo da nota no vault")


class ListNotesArgs(BaseModel):
    folder: str | None = None
    tag: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class LinkedNotesArgs(BaseModel):
    rel_path: str
    direction: LinkDirection = Field(
        default="both", description="outgoing, incoming ou both"
    )


def _guard_read(runtime: Runtime, rel_path: str) -> str:
    return assert_accessible(
        rel_path,
        runtime.config.vault.include,
        runtime.config.vault.exclude,
    )


def _tags_from_row(row: object) -> list[str]:
    try:
        raw = row["tags"]  # type: ignore[index]
        return [str(t) for t in json.loads(raw or "[]")]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def search_notes(runtime: Runtime, args: SearchNotesArgs) -> list[dict[str, object]]:
    chunks = runtime.retrieval.search(
        args.query,
        top_k=args.top_k,
        folder=args.folder,
        tags=args.tags,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    return [
        {
            "chunk_id": c.chunk_id,
            "file_id": c.file_id,
            "rel_path": c.rel_path,
            "title": c.title,
            "heading_path": c.heading_path,
            "content": c.content,
            "score": round(c.score, 4),
            "citation": c.citation(),
            "start_line": c.start_line,
            "end_line": c.end_line,
            "ordinal": c.ordinal,
            "tags": list(c.tags),
            "folder": c.folder,
        }
        for c in chunks
    ]


def read_note(runtime: Runtime, args: ReadNoteArgs) -> dict[str, object]:
    posix = _guard_read(runtime, args.rel_path)
    try:
        parsed = runtime.reader.parse(posix)
    except NoteNotFoundError:
        raise
    except VaultError:
        raise
    return NoteContent(
        rel_path=posix,
        title=parsed.title,
        content=parsed.raw,
        frontmatter=parsed.frontmatter,
        tags=parsed.tags,
        links=[link.display() for link in parsed.links],
    ).__dict__


def list_notes(runtime: Runtime, args: ListNotesArgs) -> list[dict[str, object]]:
    rows = runtime.store.list_notes(folder=args.folder, tag=args.tag, limit=args.limit)
    refs: list[NoteRef] = []
    for row in rows:
        rel = str(row["rel_path"])
        if not is_included(rel, runtime.config.vault.include, runtime.config.vault.exclude):
            continue
        tags = _tags_from_row(row)
        refs.append(NoteRef(rel_path=rel, title=str(row["title"] or ""), tags=tags))
    return [{"rel_path": r.rel_path, "title": r.title, "tags": r.tags} for r in refs]


def get_linked_notes(runtime: Runtime, args: LinkedNotesArgs) -> list[dict[str, object]]:
    posix = _guard_read(runtime, args.rel_path)
    refs = runtime.graph.neighbors(posix, args.direction)
    return [{"rel_path": r.rel_path, "title": r.title, "tags": r.tags} for r in refs]
