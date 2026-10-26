"""Integração: conectar clientes MCP e ver o tráfego gravado pelo servidor."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from nix.core.admin.client_config import client_snippets
from nix.core.admin.doctor import nix_command
from nix.core.admin.traffic import TrafficCall, TrafficStore, TrafficSummary
from nix.core.tools.registry import SPECS
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
class TrafficView:
    calls: list[TrafficCall]
    summary: TrafficSummary
    tools: list[str]
    error: str | None


async def connect_page(request: Request) -> Response:
    command, problem = await asyncio.to_thread(nix_command)
    return page(
        request,
        "connect.html",
        {
            "title": "Conectar cliente",
            "active": "connect",
            "command": command,
            "problem": problem,
            "snippets": client_snippets(command) if command else [],
            "tools": [_tool_view(spec.name, spec.description, spec.read_only, spec.destructive) for spec in SPECS],
        },
    )


async def traffic_page(request: Request) -> Response:
    tool = query(request, "tool")
    status = query(request, "status")
    if status not in ("", "ok", "error"):
        status = ""
    view = await asyncio.to_thread(_traffic, tool, status)
    log_prompts = web_state(request).gate.host.runtime.config.logging.log_prompts
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
