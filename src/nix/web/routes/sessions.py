"""Sessões dos agentes: lista por projeto e agente, nota, handoff pendente e hooks (RF-140)."""

from __future__ import annotations

import asyncio
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from nix.core.admin import agent_hooks
from nix.core.runtime import RuntimeHost
from nix.core.sessions.events import find_project
from nix.core.sessions.handoff import planned_note_path
from nix.core.sessions.render import build_note
from nix.core.sessions.store import HandoffRow, ProjectRow, SessionRow, SessionStore
from nix.web.render import page
from nix.web.routes.common import form_data, query
from nix.web.state import web_state

# Linhas mostradas na tabela; os totais e as contagens por agente vêm do banco inteiro.
_LIST_LIMIT = 500


@dataclass(frozen=True)
class AgentCount:
    key: str
    label: str
    count: int


@dataclass(frozen=True)
class SessionsView:
    enabled: bool
    vault: str
    folder: str
    search_default: str
    projects: list[ProjectRow]
    project: str
    agent: str
    agents: list[AgentCount]
    total: int
    rows: list[SessionRow]
    selected: SessionRow | None
    note_preview: str
    pending: HandoffRow | None
    hooks: list[agent_hooks.AgentStatus]
    with_notes: int


async def sessions_page(request: Request) -> Response:
    host = web_state(request).gate.host
    view = await asyncio.to_thread(
        _build, host, query(request, "project"), query(request, "agent"), query(request, "session")
    )
    return page(
        request,
        "sessions.html",
        {
            "title": "Sessões",
            "active": "sessions",
            "view": view,
            "message": query(request, "msg"),
        },
    )


async def handoff_cancel(request: Request) -> Response:
    form = await form_data(request)
    project = form.get("project", "")
    done = False
    if project:
        done = await asyncio.to_thread(SessionStore().cancel_handoff, project)
    note = "Handoff cancelado." if done else "Não havia handoff pendente neste projeto."
    target = f"/sessions?project={urllib.parse.quote(project)}&msg={urllib.parse.quote(note)}"
    return RedirectResponse(target, status_code=303)


def _build(host: RuntimeHost, project: str, agent: str, session_key: str) -> SessionsView:
    host.before_call()
    cfg = host.config.sessions
    store = SessionStore()
    projects = store.projects()

    here = find_project("")[0]
    known = {item.project for item in projects}
    if not project or (project not in known and project != here):
        project = here if here in known or not projects else projects[0].project

    per_agent = store.agent_counts(project)
    labels = {spec.key: spec.label for spec in agent_hooks.SPECS}
    counts = [AgentCount(key, labels[key], per_agent[key]) for key in labels if per_agent.get(key)]
    rows = store.list_sessions(project=project, agent=agent or None, limit=_LIST_LIMIT)
    selected = next((row for row in rows if row.key == session_key), rows[0] if rows else None)

    preview = ""
    if selected is not None:
        note = planned_note_path(cfg.folder, selected)
        preview = build_note(selected, store.events_for(selected.key), note_path=note, max_bytes=cfg.max_note_bytes)

    return SessionsView(
        enabled=cfg.enabled,
        vault=cfg.vault.strip(),
        folder=cfg.folder,
        search_default=cfg.search_default,
        projects=projects,
        project=project,
        agent=agent,
        agents=counts,
        total=store.count_sessions(project),
        rows=rows,
        selected=selected,
        note_preview=preview,
        pending=store.pending_handoff(project),
        hooks=agent_hooks.status(Path(project), project, store),
        with_notes=store.count_sessions(project, rendered_only=True),
    )
