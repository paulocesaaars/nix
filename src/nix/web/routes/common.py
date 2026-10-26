"""Utilitários compartilhados pelas rotas da interface."""

from __future__ import annotations

import asyncio
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Generic, TypeVar

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from nix.core.errors import NixError
from nix.core.runtime import Runtime
from nix.web.jobs import RuntimeGate
from nix.web.render import page
from nix.web.state import web_state

T = TypeVar("T")

BUSY = "Já existe uma sincronização em andamento. Espere ela terminar."
BUSY_READ = "O índice está em uso por uma sincronização. Espere ela terminar e atualize a página."


@dataclass(frozen=True)
class Gated(Generic[T]):
    """Resultado de uma chamada ao runtime: valor, aviso do processo ou erro com a ação corretiva."""

    value: T | None
    notice: str | None
    error: str | None


def gated(gate: RuntimeGate, fn: Callable[[Runtime], T], *, busy: str = BUSY_READ) -> Gated[T]:
    if not gate.lock.acquire(blocking=False):
        return Gated(None, None, busy)
    try:
        notice = gate.host.before_call()
        try:
            return Gated(fn(gate.host.runtime), notice, None)
        except NixError as exc:
            return Gated(None, notice, exc.message)
        except ValidationError as exc:
            message = f"Parâmetros inválidos: {_validation_text(exc)}. Corrija o formulário e tente de novo."
            return Gated(None, notice, message)
    finally:
        gate.lock.release()


async def run_gated(request: Request, fn: Callable[[Runtime], T], *, busy: str = BUSY_READ) -> Gated[T]:
    return await asyncio.to_thread(partial(gated, web_state(request).gate, fn, busy=busy))


async def form_data(request: Request) -> dict[str, str]:
    raw = await request.body()
    parsed = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def is_hx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def note(request: Request, message: str, *, status_code: int, active: str = "") -> Response:
    context = {"message": message, "title": "Nix", "active": active}
    if is_hx(request):
        return page(request, "fragment_message.html", context, status_code=status_code)
    return page(request, "message.html", context, status_code=status_code)


def query(request: Request, name: str) -> str:
    return request.query_params.get(name, "").strip()


def merge(notice: str | None, message: str) -> str:
    if notice:
        return f"{notice} {message}"
    return message


def _validation_text(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        where = ".".join(str(item) for item in error.get("loc", ()))
        parts.append(f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", "")))
    return "; ".join(parts)
