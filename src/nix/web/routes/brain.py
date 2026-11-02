"""Painel, caixa de entrada, perfil e abas do projeto no Mega Brain."""

from __future__ import annotations

from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import Response

from nix.core.brain.agents import AGENT_LABELS
from nix.core.brain.limits import load_brain_flags
from nix.core.brain.store import BrainStore, ProjectRecord, SessionRecord
from nix.web.render import page
from nix.web.routes.common import query

_TABS: tuple[tuple[str, str], ...] = (
    ("visao", "Visão geral"),
    ("agentes", "Agentes"),
    ("tokens", "Tokens"),
    ("sessoes", "Sessões"),
    ("conhecimento", "Conhecimento"),
)
_TAB_IDS = {item[0] for item in _TABS}


async def panel_page(request: Request) -> Response:
    needle = query(request, "q")
    store = BrainStore()
    cards = []
    for project in store.list_projects():
        sessions = store.sessions_for(project.key)
        if not sessions:
            continue
        if needle and needle.casefold() not in project.name.casefold():
            continue
        agents = list(dict.fromkeys(row.agent for row in sessions))
        cards.append(
            {
                "key": project.key,
                "name": project.name,
                "sessions": len(sessions),
                "agents": ", ".join(agents),
                "updated": sessions[0].updated_at,
                "href": _project_href(project.key, "visao"),
            }
        )
    flags = load_brain_flags()
    return page(
        request,
        "brain.html",
        {
            "title": "Mega Brain",
            "active": "brain",
            "q": needle,
            "cards": cards,
            "enabled": flags.enabled,
            "wiki_name": flags.wiki,
        },
    )


async def inbox_page(request: Request) -> Response:
    store = BrainStore()
    names = {item.key: item.name for item in store.list_projects()}
    rows = []
    for message_id, project_key, recipient, body, status in store.list_all_messages():
        rows.append(
            {
                "id": message_id,
                "project": names.get(project_key, project_key or "qualquer"),
                "recipient": recipient or "qualquer agente",
                "body": body,
                "status": _message_status(status),
            }
        )
    return page(
        request,
        "brain_inbox.html",
        {"title": "Caixa de entrada", "active": "inbox", "messages": rows},
    )


async def profile_page(request: Request) -> Response:
    store = BrainStore()
    rows = [
        {
            "category": item.category,
            "sentence": item.sentence,
            "page": item.page_path,
            "href": "/notes/view?path=" + quote(item.page_path),
        }
        for item in store.list_profile("active")
    ]
    return page(
        request,
        "brain_profile.html",
        {
            "title": "Perfil",
            "active": "profile",
            "entries": rows,
            "brain_wiki": load_brain_flags().wiki,
        },
    )


async def project_page(request: Request) -> Response:
    key = query(request, "project")
    tab = query(request, "tab") or "visao"
    if tab not in _TAB_IDS:
        tab = "visao"
    store = BrainStore()
    project = next((item for item in store.list_projects() if item.key == key), None)
    if project is None:
        return page(
            request,
            "brain_project.html",
            {
                "title": "Projeto",
                "active": "brain",
                "missing": True,
                "project": None,
                "tab": tab,
                "tabs": [],
            },
            status_code=404,
        )
    sessions = store.sessions_for(project.key)
    return page(
        request,
        "brain_project.html",
        {
            "title": project.name,
            "active": "brain",
            "missing": False,
            "project": _project_view(store, project, sessions),
            "tab": tab,
            "brain_wiki": load_brain_flags().wiki,
            "tabs": [
                {"id": item_id, "label": label, "href": _project_href(project.key, item_id)}
                for item_id, label in _TABS
            ],
        },
    )


def _project_view(store: BrainStore, project: ProjectRecord, sessions: list[SessionRecord]) -> dict[str, object]:
    agents: dict[str, int] = {}
    for row in sessions:
        agents[row.agent] = agents.get(row.agent, 0) + 1
    offered = store.offered_handoff(project.key)
    pages = [row for row in sessions if row.page_path]
    return {
        "key": project.key,
        "name": project.name,
        "sessions": len(sessions),
        "open_sessions": sum(1 for row in sessions if row.status == "open"),
        "agents": [{"name": name, "sessions": count} for name, count in agents.items()],
        "hooks": [{"agent": agent, "scope": scope} for agent, scope in store.installed_agents(project.key)],
        "tokens": [
            {
                "agent": item.agent,
                "label": AGENT_LABELS.get(item.agent, item.agent),
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
            }
            for item in store.token_usage_by_agent(project.key)
        ],
        "session_rows": [
            {
                "agent": row.agent,
                "external_id": row.external_id,
                "status": "aberta" if row.status == "open" else "encerrada",
                "updated": row.updated_at,
                "page": row.page_path,
            }
            for row in sessions
        ],
        "pages": [
            {
                "path": row.page_path,
                "agent": row.agent,
                "href": "/notes/view?path=" + quote(row.page_path),
            }
            for row in pages
        ],
        "handoff": offered.body if offered is not None else "",
        "messages": store.pending_messages(project.key),
    }


def _project_href(key: str, tab: str) -> str:
    return f"/brain/project?project={quote(key)}&tab={tab}"


def _message_status(status: str) -> str:
    labels = {"pending": "esperando", "delivered": "entregue", "cancelled": "cancelada"}
    return labels.get(status, status)
