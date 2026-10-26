"""Estado do processo da interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from starlette.requests import Request

from nix.web.jobs import RuntimeGate, SyncJobs


class ServerControl(Protocol):
    should_exit: bool


@dataclass
class WebState:
    token: str
    port: int
    gate: RuntimeGate
    jobs: SyncJobs
    server: ServerControl | None = None


def web_state(request: Request) -> WebState:
    state = request.app.state.web
    if not isinstance(state, WebState):
        raise RuntimeError("Estado da interface indisponível. Feche e abra de novo o nix ui.")
    return state
