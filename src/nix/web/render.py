"""Templates Jinja2 com autoescape."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from nix.web.state import WebState

_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _csrf(request: Request) -> dict[str, Any]:
    state = request.app.state.web
    token = state.token if isinstance(state, WebState) else ""
    return {"csrf_token": token}


templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates",
    context_processors=[_csrf],
)


def page(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    background: BackgroundTask | None = None,
) -> Response:
    return templates.TemplateResponse(
        request,
        name,
        context or {},
        status_code=status_code,
        headers=_HEADERS,
        background=background,
    )


def fragment(name: str, **context: Any) -> str:
    return templates.get_template(name).render(**context)
