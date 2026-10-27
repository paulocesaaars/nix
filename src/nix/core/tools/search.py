"""Ferramentas de busca e leitura de notas."""

from __future__ import annotations

import json

from pydantic import Field

from nix.core.errors import NoteNotFoundError, VaultError
from nix.core.models import Heading, LinkDirection, NoteContent, NoteLines, NoteOutline, NoteRef
from nix.core.runtime import Runtime
from nix.core.tools.args import MultiVaultArgs, VaultArgs
from nix.core.vault.markdown import headings_in_file, split_frontmatter
from nix.core.vault.paths import assert_accessible, is_included

_MAX_NOTE_LINES = 400


class SearchNotesArgs(MultiVaultArgs):
    query: str = Field(description="Consulta em linguagem natural ou termos-chave")
    top_k: int = Field(default=5, ge=1, le=50)
    folder: str | None = Field(default=None, description="Pasta relativa ao vault")
    tags: list[str] | None = Field(default=None)
    date_from: str | None = Field(default=None, description="ISO YYYY-MM-DD")
    date_to: str | None = Field(default=None, description="ISO YYYY-MM-DD")


class ReadNoteArgs(VaultArgs):
    rel_path: str = Field(description="Caminho relativo da nota no vault")


class ListNotesArgs(MultiVaultArgs):
    folder: str | None = None
    tag: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class LinkedNotesArgs(VaultArgs):
    rel_path: str
    direction: LinkDirection = Field(
        default="both", description="outgoing, incoming ou both"
    )


class ReadNoteLinesArgs(VaultArgs):
    rel_path: str = Field(description="Caminho relativo da nota no vault")
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="Linha inicial do arquivo (1 = primeira linha, frontmatter incluído)",
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
        description="Linha final do arquivo, inclusive. Omita para ir até o fim (com limite de 400).",
    )
    heading: str | None = Field(
        default=None,
        description='Heading exato ("Seção") ou caminho ("Pai > Filho"). Tem prioridade sobre o intervalo.',
    )


class GetNoteOutlineArgs(VaultArgs):
    rel_path: str = Field(description="Caminho relativo da nota no vault")


class ListAllTagsArgs(MultiVaultArgs):
    folder: str | None = Field(default=None, description="Pasta relativa ao vault")
    limit: int = Field(default=200, ge=1, le=1000)


# list_tags exige um teto e corta cada vault antes da soma. O limite do usuário
# só entra na lista já somada; este teto evita que uma tag frequente no total
# suma ou perca contagem quando um vault sozinho passa do limite pedido.
_TAG_SCAN_LIMIT = 100_000


def _guard_read(runtime: Runtime, rel_path: str) -> str:
    vault = runtime.vault
    return assert_accessible(
        rel_path,
        vault.include,
        vault.exclude,
    )


def _tags_from_row(row: object) -> list[str]:
    try:
        raw = row["tags"]  # type: ignore[index]
        return [str(t) for t in json.loads(raw or "[]")]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def _body_offset(runtime: Runtime, rel_path: str, cache: dict[str, int]) -> int:
    """Linhas do índice são do corpo. Soma o deslocamento para a linha do arquivo bruto."""
    if rel_path in cache:
        return cache[rel_path]
    if not rel_path.lower().endswith(".md"):
        cache[rel_path] = 0
        return 0
    try:
        raw = runtime.reader.read_text(rel_path, keep_newlines=True)
    except VaultError:
        cache[rel_path] = 0
        return 0
    cache[rel_path] = split_frontmatter(raw).body_line_offset
    return cache[rel_path]


def _file_line(line: int | None, offset: int) -> int | None:
    if line is None:
        return None
    return line + offset


def search_notes(runtimes: list[Runtime], args: SearchNotesArgs) -> dict[str, object]:
    from nix.core.retrieval.service import search_many

    by_name = {runtime.vault.name: runtime for runtime in runtimes}
    outcome = search_many(
        [(runtime.vault.name, runtime.retrieval) for runtime in runtimes],
        args.query,
        top_k=args.top_k,
        folder=args.folder,
        tags=args.tags,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    offsets: dict[tuple[str, str], int] = {}
    rows: list[dict[str, object]] = []
    for chunk in outcome.chunks:
        runtime = by_name.get(chunk.vault) or runtimes[0]
        key = (chunk.vault, chunk.rel_path)
        if key not in offsets:
            offsets[key] = _body_offset(runtime, chunk.rel_path, {})
        offset = offsets[key]
        rows.append(
            {
                "vault": chunk.vault,
                "chunk_id": chunk.chunk_id,
                "file_id": chunk.file_id,
                "rel_path": chunk.rel_path,
                "title": chunk.title,
                "heading_path": chunk.heading_path,
                "content": chunk.content,
                "score": round(chunk.score, 4),
                "citation": chunk.citation(),
                "start_line": _file_line(chunk.start_line, offset),
                "end_line": _file_line(chunk.end_line, offset),
                "ordinal": chunk.ordinal,
                "tags": list(chunk.tags),
                "folder": chunk.folder,
            }
        )
    return {
        "vault": [runtime.vault.name for runtime in runtimes],
        "results": rows,
        "vault_errors": outcome.vault_errors,
    }


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


def _load_note_text(runtime: Runtime, rel_path: str) -> tuple[str, str]:
    posix = _guard_read(runtime, rel_path)
    runtime.writer.resolve(posix)
    return posix, runtime.reader.read_text(posix, keep_newlines=True)


def _match_heading(headings: list[Heading], query: str, rel_path: str) -> Heading:
    wanted = query.strip()
    for heading in headings:
        if heading.path == wanted:
            return heading
    by_title = [heading for heading in headings if heading.title == wanted]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        raise VaultError(
            f"Há mais de um heading {wanted!r} em {rel_path}. "
            'Use o caminho "Pai > Filho" ou use get_note_outline para ver os headings.'
        )
    raise VaultError(
        f"O heading {wanted!r} não existe em {rel_path}; use get_note_outline para ver os headings."
    )


def _heading_dict(heading: Heading) -> dict[str, object]:
    return {
        "level": heading.level,
        "title": heading.title,
        "path": heading.path,
        "start_line": heading.start_line,
        "end_line": heading.end_line,
    }


def get_note_outline(runtime: Runtime, args: GetNoteOutlineArgs) -> dict[str, object]:
    posix, raw = _load_note_text(runtime, args.rel_path)
    parsed = runtime.reader.parse(posix)
    headings, _offset = headings_in_file(raw)
    outline = NoteOutline(
        rel_path=posix,
        title=parsed.title,
        frontmatter_keys=[str(key) for key in parsed.frontmatter],
        line_count=len(raw.splitlines()),
        headings=headings,
    )
    return {
        "rel_path": outline.rel_path,
        "title": outline.title,
        "frontmatter_keys": list(outline.frontmatter_keys),
        "line_count": outline.line_count,
        "headings": [_heading_dict(heading) for heading in outline.headings],
    }


def read_note_lines(runtime: Runtime, args: ReadNoteLinesArgs) -> dict[str, object]:
    posix, raw = _load_note_text(runtime, args.rel_path)
    file_lines = raw.splitlines()
    total = len(file_lines)
    heading_label: str | None = None
    if args.heading and args.heading.strip():
        headings, _offset = headings_in_file(raw)
        matched = _match_heading(headings, args.heading, posix)
        start = matched.start_line
        end = matched.end_line
        heading_label = matched.path
    else:
        start = args.start_line if args.start_line is not None else 1
        end = args.end_line if args.end_line is not None else total
    if total == 0:
        result = NoteLines(
            rel_path=posix,
            start_line=1,
            end_line=0,
            content="",
            truncated=False,
            line_count=0,
            next_start_line=None,
            heading=heading_label,
        )
        return _lines_dict(result)
    if start > total:
        raise VaultError(
            f"start_line {start} está fora de {posix} ({total} linhas). "
            "Use get_note_outline para ver o total de linhas e os headings."
        )
    if start < 1:
        start = 1
    if end > total:
        end = total
    if end < start:
        raise VaultError(
            f"end_line {end} é menor que start_line {start} em {posix}. "
            "Informe um intervalo crescente ou use get_note_outline para ver os headings."
        )
    truncated = False
    next_start: int | None = None
    if end - start + 1 > _MAX_NOTE_LINES:
        end = start + _MAX_NOTE_LINES - 1
        truncated = True
        next_start = end + 1
    result = NoteLines(
        rel_path=posix,
        start_line=start,
        end_line=end,
        content="\n".join(file_lines[start - 1 : end]),
        truncated=truncated,
        line_count=total,
        next_start_line=next_start,
        heading=heading_label,
    )
    return _lines_dict(result)


def _lines_dict(result: NoteLines) -> dict[str, object]:
    return {
        "rel_path": result.rel_path,
        "start_line": result.start_line,
        "end_line": result.end_line,
        "content": result.content,
        "truncated": result.truncated,
        "line_count": result.line_count,
        "next_start_line": result.next_start_line,
        "heading": result.heading,
    }


def list_all_tags(runtimes: list[Runtime], args: ListAllTagsArgs) -> dict[str, object]:
    """Soma as contagens e guarda o detalhe de cada vault."""
    totals: dict[str, int] = {}
    labels: dict[str, str] = {}
    detail: dict[str, list[dict[str, object]]] = {}
    for runtime in runtimes:
        include = runtime.vault.include
        exclude = runtime.vault.exclude

        def path_ok(rel: str, include: list[str] = include, exclude: list[str] = exclude) -> bool:
            return is_included(rel, include, exclude)

        for tag, count in runtime.store.list_tags(folder=args.folder, limit=_TAG_SCAN_LIMIT, path_ok=path_ok):
            key = tag.casefold()
            labels.setdefault(key, tag)
            totals[key] = totals.get(key, 0) + count
            detail.setdefault(key, []).append({"vault": runtime.vault.name, "count": count})
    tags = sorted(totals, key=lambda key: (-totals[key], labels[key].casefold()))
    return {
        "vault": [runtime.vault.name for runtime in runtimes],
        "tags": [
            {"tag": labels[key], "count": totals[key], "vaults": detail[key]}
            for key in tags[: args.limit]
        ],
    }


def list_notes(runtimes: list[Runtime], args: ListNotesArgs) -> dict[str, object]:
    notes: list[dict[str, object]] = []
    for runtime in runtimes:
        rows = runtime.store.list_notes(folder=args.folder, tag=args.tag, limit=args.limit)
        for row in rows:
            rel = str(row["rel_path"])
            if not is_included(rel, runtime.vault.include, runtime.vault.exclude):
                continue
            tags = _tags_from_row(row)
            ref = NoteRef(rel_path=rel, title=str(row["title"] or ""), tags=tags)
            notes.append(
                {"vault": runtime.vault.name, "rel_path": ref.rel_path, "title": ref.title, "tags": ref.tags}
            )
    return {"vault": [runtime.vault.name for runtime in runtimes], "notes": notes}


def get_linked_notes(runtime: Runtime, args: LinkedNotesArgs) -> list[dict[str, object]]:
    posix = _guard_read(runtime, args.rel_path)
    refs = runtime.graph.neighbors(posix, args.direction)
    return [{"rel_path": r.rel_path, "title": r.title, "tags": r.tags} for r in refs]
