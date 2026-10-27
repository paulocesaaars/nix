"""Templates Jinja2 com autoescape."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from markupsafe import Markup, escape
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from nix.web.state import WebState

_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "same-origin"}


_WORD = re.compile(r"\w{3,}")


def _vault_url(path: str, name: str) -> str:
    if not name:
        return path
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}vault={quote(name)}"


def _csrf(request: Request) -> dict[str, Any]:
    from nix import __version__
    from nix.core.errors import NixError

    state = request.app.state.web
    token = state.token if isinstance(state, WebState) else ""
    context: dict[str, Any] = {
        "csrf_token": token,
        "nix_version": __version__,
        "vault_label": "",
        "vaults": [],
        "selected_vault": "",
        "vault_error": "",
        "kept_params": [],
        "vault_url": lambda path, vault=None: path,  # noqa: ARG005
    }
    if not isinstance(state, WebState):
        return context
    host = state.gate.host
    try:
        host.before_call()
        config = host.config
        if not config.vaults:
            return context
        default_name = config.default_vault.name
    except NixError as exc:
        context["vault_error"] = exc.message
        return context
    except Exception:  # noqa: BLE001
        return context
    raw = request.query_params.get("vault", "").strip()
    selected = default_name
    if raw and raw != "*":
        try:
            selected = config.get_vault(raw).name
        except NixError as exc:
            context["vault_error"] = exc.message
    label = ""
    try:
        label = config.get_vault(selected).path
    except NixError:
        label = ""
    kept = [(key, value) for key, value in request.query_params.multi_items() if key != "vault"]

    def vault_url(path: str, vault: str | None = None) -> str:
        return _vault_url(path, (vault or selected).strip())

    context.update(
        vault_label=label,
        vaults=[
            {"name": vault.name, "path": vault.path, "is_default": vault.is_default} for vault in config.vaults
        ],
        selected_vault=selected,
        kept_params=kept,
        vault_url=vault_url,
    )
    return context


def when(value: object) -> str:
    """ISO 8601 no fuso local, no formato dd/mm/aaaa hh:mm."""
    if not value:
        return "—"
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d/%m/%Y %H:%M")


def num(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{int(value):,}".replace(",", ".")


def duration(ms: object) -> str:
    if not isinstance(ms, int | float):
        return "—"
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.1f} s".replace(".", ",")


def filesize(size: object) -> str:
    if not isinstance(size, int | float):
        return "—"
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB".replace(".", ",")
    return f"{size / 1024 / 1024:.1f} MB".replace(".", ",")


def highlight(text: object, query: object) -> Markup:
    """Escapa o texto e marca os termos da busca com <mark>."""
    raw = str(text or "")
    terms = {word.lower() for word in _WORD.findall(str(query or ""))}
    if not terms:
        return escape(raw)
    pattern = re.compile("|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    parts: list[str] = []
    last = 0
    for match in pattern.finditer(raw):
        parts.append(str(escape(raw[last : match.start()])))
        parts.append(f"<mark>{escape(match.group(0))}</mark>")
        last = match.end()
    parts.append(str(escape(raw[last:])))
    return Markup("".join(parts))


templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates",
    context_processors=[_csrf],
)
templates.env.filters.update(when=when, num=num, duration=duration, filesize=filesize, highlight=highlight)


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
    """Fragmentos do SSE: sem request, então sem o context processor."""
    rendered = templates.get_template(name).render(**context)
    return str(rendered)
