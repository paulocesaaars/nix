"""Consultas ao vault pela mesma definição das ferramentas MCP (só leitura)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import Response

from nix.core.runtime import Runtime, RuntimeHost
from nix.core.tools.registry import call_tool
from nix.web.jobs import RuntimeGate
from nix.web.render import page
from nix.web.routes.common import is_hx, query, run_gated
from nix.web.state import web_state

_KINDS = ("summary", "orphans", "duplicates", "links")
_EXCERPT_LINES = 60


@dataclass(frozen=True)
class SearchForm:
    q: str
    folder: str
    tags: str
    date_from: str
    date_to: str
    top_k: int

    def payload(self) -> dict[str, Any]:
        tags = [item.strip().lstrip("#") for item in self.tags.split(",") if item.strip()]
        return {
            "query": self.q,
            "top_k": self.top_k,
            "folder": self.folder or None,
            "tags": tags or None,
            "date_from": self.date_from or None,
            "date_to": self.date_to or None,
        }


@dataclass(frozen=True)
class NoteDetail:
    outline: dict[str, Any]
    excerpt: dict[str, Any]
    outgoing: list[dict[str, Any]]
    incoming: list[dict[str, Any]]


@dataclass(frozen=True)
class NotesIndex:
    notes: list[dict[str, Any]]
    errors: list[str]


async def search_page(request: Request) -> Response:
    form = _search_form(request)
    spec, chosen, all_vaults = _search_spec(request)
    results: list[dict[str, Any]] = []
    vault_errors: list[dict[str, Any]] = []
    error: str | None = None
    notice: str | None = None
    if form.q:
        found, notice, error = await asyncio.to_thread(_search, web_state(request).gate, spec, form.payload())
        results = found.get("results", [])
        vault_errors = found.get("vault_errors", [])
    context = {
        "form": form,
        "results": results,
        "vault_errors": vault_errors,
        "chosen_vaults": chosen,
        "all_vaults": all_vaults,
        "error": error,
        "notice": notice,
    }
    if is_hx(request):
        return page(request, "search_results.html", context)
    context.update(title="Busca", active="search")
    return page(request, "search.html", context)


async def notes_page(request: Request) -> Response:
    folder = query(request, "folder")
    tag = query(request, "tag").lstrip("#")
    result = await run_gated(request, lambda runtime: _notes_index(web_state(request).gate.host, runtime, folder, tag))
    return page(
        request,
        "notes.html",
        {
            "title": "Notas",
            "active": "notes",
            "folder": folder,
            "tag": tag,
            "index": result.value,
            "error": result.error,
            "notice": result.notice,
        },
    )


async def note_view(request: Request) -> Response:
    path = query(request, "path")
    heading = query(request, "heading")
    start = _int(query(request, "start"), 1)
    if not path:
        return page(
            request,
            "message.html",
            {"title": "Notas", "active": "notes", "message": "Escolha uma nota na lista de notas."},
            status_code=400,
        )
    result = await run_gated(
        request, lambda runtime: _note_detail(web_state(request).gate.host, runtime, path, heading, start)
    )
    return page(
        request,
        "note.html",
        {
            "title": path,
            "active": "notes",
            "path": path,
            "heading": heading,
            "detail": result.value,
            "error": result.error,
            "notice": result.notice,
        },
    )


async def tags_page(request: Request) -> Response:
    folder = query(request, "folder")
    payload = {"folder": folder or None, "limit": 1000}
    result = await run_gated(
        request, lambda runtime: _tool_dict(web_state(request).gate.host, runtime, "list_all_tags", payload)
    )
    raw_tags = result.value or {}
    tags = raw_tags.get("tags") if isinstance(raw_tags, dict) else []
    if not isinstance(tags, list):
        tags = []
    top = max((int(item["count"]) for item in tags), default=0)
    return page(
        request,
        "tags.html",
        {
            "title": "Tags",
            "active": "tags",
            "folder": folder,
            "tags": tags,
            "top": top,
            "total": sum(int(item["count"]) for item in tags),
            "error": result.error,
            "notice": result.notice,
        },
    )


async def insights_page(request: Request) -> Response:
    kind = query(request, "kind") or "summary"
    if kind not in _KINDS:
        kind = "summary"
    payload = {"kind": kind, "limit": 100}
    result = await run_gated(
        request, lambda runtime: _tool_dict(web_state(request).gate.host, runtime, "vault_insights", payload)
    )
    data = result.value or {}
    return page(
        request,
        "insights.html",
        {
            "title": "Insights",
            "active": "insights",
            "kind": kind,
            "items": data.get("items"),
            "error": result.error,
            "notice": result.notice,
        },
    )


def _tool_dict(host: RuntimeHost, runtime: Runtime, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    merged = {**payload, "vault": runtime.vault.name}
    found = call_tool(host, name, merged)
    return found if isinstance(found, dict) else {}


def _tool_list(host: RuntimeHost, runtime: Runtime, name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    found = call_tool(host, name, {**payload, "vault": runtime.vault.name})
    if isinstance(found, dict) and isinstance(found.get("notes"), list):
        return cast(list[dict[str, Any]], found["notes"])
    if isinstance(found, list):
        return cast(list[dict[str, Any]], found)
    return []


def _notes_index(host: RuntimeHost, runtime: Runtime, folder: str, tag: str) -> NotesIndex:
    notes = _tool_list(host, runtime, "list_notes", {"folder": folder or None, "tag": tag or None, "limit": 500})
    errors = [] if folder or tag else [str(row["rel_path"]) for row in runtime.store.error_files()]
    return NotesIndex(notes=notes, errors=errors)


def _note_detail(host: RuntimeHost, runtime: Runtime, path: str, heading: str, start: int) -> NoteDetail:
    outline = _tool_dict(host, runtime, "get_note_outline", {"rel_path": path})
    if heading:
        lines_args: dict[str, Any] = {"rel_path": path, "heading": heading}
    else:
        lines_args = {"rel_path": path, "start_line": start, "end_line": start + _EXCERPT_LINES - 1}
    excerpt = _tool_dict(host, runtime, "read_note_lines", lines_args)
    outgoing = _tool_list(host, runtime, "get_linked_notes", {"rel_path": path, "direction": "outgoing"})
    incoming = _tool_list(host, runtime, "get_linked_notes", {"rel_path": path, "direction": "incoming"})
    return NoteDetail(outline=outline, excerpt=excerpt, outgoing=outgoing, incoming=incoming)


def _search_spec(request: Request) -> tuple[str | list[str] | None, set[str], bool]:
    values = [item.strip() for key, item in request.query_params.multi_items() if key == "vault" and item.strip()]
    if not values:
        return None, set(), False
    if any(item == "*" for item in values):
        return "*", set(), True
    return values, {item.casefold() for item in values}, False


def _search(
    gate: RuntimeGate, spec: str | list[str] | None, payload: dict[str, Any]
) -> tuple[dict[str, Any], str | None, str | None]:
    with gate.borrow(spec) as borrowed:
        if borrowed.error:
            return {}, borrowed.notice, borrowed.error
        if not borrowed.runtimes:
            message = borrowed.skipped[0]["message"] if borrowed.skipped else "Nenhum vault disponível para a busca."
            return {"results": [], "vault_errors": borrowed.skipped}, borrowed.notice, message
        names = [runtime.vault.name for runtime in borrowed.runtimes]
        found = call_tool(gate.host, "search_notes", {**payload, "vault": names})
        if not isinstance(found, dict):
            return {}, borrowed.notice, "A busca não devolveu um resultado. Rode `nix sync` e tente de novo."
        errors = found.get("vault_errors")
        merged = list(errors) if isinstance(errors, list) else []
        merged.extend(borrowed.skipped)
        found["vault_errors"] = merged
        results = found.get("results")
        if not isinstance(results, list):
            found["results"] = []
        return found, borrowed.notice, None


def _search_form(request: Request) -> SearchForm:
    return SearchForm(
        q=query(request, "q"),
        folder=query(request, "folder"),
        tags=query(request, "tags"),
        date_from=query(request, "date_from"),
        date_to=query(request, "date_to"),
        top_k=min(max(_int(query(request, "top_k"), 8), 1), 50),
    )


def _int(raw: str, default: int) -> int:
    try:
        return max(int(raw), 1)
    except ValueError:
        return default
