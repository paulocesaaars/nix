"""Integração: conectar clientes MCP e ver o tráfego gravado pelo servidor."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from nix.config.executables import packaged_hook_executable
from nix.core.admin import agent_hooks
from nix.core.admin.client_config import client_snippets
from nix.core.admin.doctor import nix_command
from nix.core.admin.traffic import TrafficCall, TrafficStore, TrafficSummary
from nix.core.sessions.events import find_project
from nix.core.sessions.store import SessionStore
from nix.core.tools.registry import active_specs
from nix.web.render import page
from nix.web.routes.common import query
from nix.web.state import web_state


@dataclass(frozen=True)
class ToolView:
    name: str
    kind: str
    label: str
    description: str


@dataclass(frozen=True)
class HookView:
    key: str
    label: str
    file: str
    state: str
    command: str
    note: str


@dataclass(frozen=True)
class TrafficView:
    calls: list[TrafficCall]
    summary: TrafficSummary
    tools: list[str]
    error: str | None


async def connect_page(request: Request) -> Response:
    command, problem = await asyncio.to_thread(nix_command)
    host = web_state(request).gate.host
    specs = active_specs(host.config.sessions.enabled)
    project = await asyncio.to_thread(_hooks_project, query(request, "project"))
    return page(
        request,
        "connect.html",
        {
            "title": "Conectar cliente",
            "active": "connect",
            "command": command,
            "problem": problem,
            "snippets": client_snippets(command) if command else [],
            "hooks_project": project,
            "hooks": await asyncio.to_thread(_hooks, _hook_command(command), project),
            "tools": [_tool_view(spec.name, spec.description, spec.read_only, spec.destructive) for spec in specs],
        },
    )


async def traffic_page(request: Request) -> Response:
    tool = query(request, "tool")
    status = query(request, "status")
    if status not in ("", "ok", "error"):
        status = ""
    view = await asyncio.to_thread(_traffic, tool, status)
    host = web_state(request).gate.host
    host.before_call()
    log_prompts = host.config.logging.log_prompts
    return page(
        request,
        "traffic.html",
        {
            "title": "Tráfego MCP",
            "active": "traffic",
            "view": view,
            "tool": tool,
            "status": status,
            "log_prompts": log_prompts,
        },
    )


def _hooks_project(requested: str) -> str:
    """Projeto pedido em `?project=` se já tem sessão gravada; senão, a pasta onde o `nix ui` roda."""
    here = find_project("")[0]
    if requested and requested != here:
        try:
            known = {item.project for item in SessionStore().projects()}
        except sqlite3.Error:
            known = set()
        if requested in known:
            return requested
    return here


def _hook_command(fallback: str | None) -> str | None:
    """Prévia do comando que `nix hooks install` grava. No binário, é o `nix-hook`."""
    found = packaged_hook_executable()
    if found is not None:
        return str(found)
    return fallback


def _hooks(command: str | None, project: str) -> list[HookView]:
    """Por agente, o arquivo de hook que `nix hooks install` criaria e o estado neste projeto (RF-141)."""
    try:
        states = {item.spec.key: item.state for item in agent_hooks.status(Path(project), project, SessionStore())}
    except (sqlite3.Error, OSError):
        states = {}
    exe = command.replace("\\", "/") if command else ""
    return [
        HookView(
            key=spec.key,
            label=spec.label,
            file=spec.rel_path,
            state=states.get(spec.key, "inativo"),
            command=agent_hooks.command_preview(spec, exe) if exe else "",
            note=spec.note,
        )
        for spec in agent_hooks.SPECS
    ]


def _traffic(tool: str, status: str) -> TrafficView:
    store = TrafficStore()
    try:
        data = store.snapshot(200, tool=tool or None, status=status or None)
        return TrafficView(calls=data.calls, summary=data.summary, tools=data.tools, error=None)
    except (sqlite3.Error, OSError) as exc:
        return TrafficView(
            calls=[],
            summary=TrafficSummary(0, 0, 0.0, None),
            tools=[],
            error=f"Não foi possível ler {store.path}: {exc}. Feche o cliente MCP e atualize a página.",
        )


def _tool_view(name: str, description: str, read_only: bool, destructive: bool) -> ToolView:
    if destructive:
        kind, label = "err", "destrutiva"
    elif not read_only:
        kind, label = "warn", "escrita"
    else:
        kind, label = "ok", "leitura"
    return ToolView(name=name, kind=kind, label=label, description=description)
