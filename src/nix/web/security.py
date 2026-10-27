"""Restringe a interface ao navegador aberto por `nix ui` neste processo."""

from __future__ import annotations

import enum
import secrets
import urllib.parse

from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HOST_DENIED = "A interface só atende o navegador aberto por nix ui."
_ORIGIN_DENIED = (
    "O formulário veio de outra origem. Abra a interface pelo link que o nix ui imprimiu "
    "(http://127.0.0.1:PORTA/?t=...) e recarregue a página antes de enviar."
)
_COOKIE_DENIED = "É preciso abrir pelo link que o nix ui imprimiu."
_CSRF_DENIED = "Recarregue a página para continuar."
_BODY_DENIED = "O formulário passou do tamanho aceito. Reduza o conteúdo e recarregue a página."
_MAX_BODY = 2_000_000
_COOKIE = "nix_session"


class _Body(enum.Enum):
    GONE = "gone"
    LARGE = "large"


def _matches(candidate: str | None, token: str) -> bool:
    if candidate is None or len(candidate) != len(token):
        return False
    return secrets.compare_digest(candidate, token)


def _headers(scope: Scope) -> dict[bytes, bytes]:
    found: dict[bytes, bytes] = {}
    raw = scope.get("headers", [])
    if not isinstance(raw, list):
        return found
    for item in raw:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        key, value = item
        if isinstance(key, bytes) and isinstance(value, bytes):
            found[key.lower()] = value
    return found


def _header_text(headers: dict[bytes, bytes], name: bytes) -> str | None:
    raw = headers.get(name)
    if raw is None:
        return None
    return raw.decode("latin-1")


def _cookie(header: str | None, name: str) -> str | None:
    if not header:
        return None
    prefix = f"{name}="
    for part in header.split(";"):
        piece = part.strip()
        if piece.startswith(prefix):
            return piece[len(prefix) :]
    return None


def _accepted_hosts(port: int) -> set[str]:
    hosts = {f"127.0.0.1:{port}"}
    if port == 80:
        hosts.add("127.0.0.1")
    return hosts


def _accepted_origins(port: int) -> set[str]:
    origins = {f"http://127.0.0.1:{port}"}
    if port == 80:
        origins.add("http://127.0.0.1")
    return origins


def _safe_path(scope: Scope) -> str:
    raw = scope.get("path", "/")
    if isinstance(raw, str) and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


def _query_token(scope: Scope) -> str | None:
    raw = scope.get("query_string", b"")
    if not isinstance(raw, bytes) or not raw:
        return None
    parsed = urllib.parse.parse_qs(raw.decode("ascii", errors="ignore"), keep_blank_values=False)
    values = parsed.get("t")
    if not values:
        return None
    return values[0]


async def _read_body(receive: Receive) -> bytes | _Body:
    chunks: list[bytes] = []
    size = 0
    too_large = False
    while True:
        message = await receive()
        kind = message.get("type")
        if kind == "http.disconnect":
            return _Body.GONE
        if kind != "http.request":
            continue
        chunk = message.get("body", b"")
        if isinstance(chunk, bytes) and not too_large:
            size += len(chunk)
            if size > _MAX_BODY:
                too_large = True
            else:
                chunks.append(chunk)
        if not message.get("more_body", False):
            if too_large:
                return _Body.LARGE
            return b"".join(chunks)


def _csrf_field(body: bytes, content_type: str | None) -> str | None:
    if content_type and "multipart/form-data" in content_type.lower():
        return _csrf_multipart(body)
    text = body.decode("utf-8", errors="replace")
    parsed = urllib.parse.parse_qs(text, keep_blank_values=True)
    values = parsed.get("csrf")
    if not values:
        return None
    return values[-1]


def _csrf_multipart(body: bytes) -> str | None:
    marker = b'name="csrf"'
    start = body.find(marker)
    if start < 0:
        return None
    separator = body.find(b"\r\n\r\n", start)
    if separator < 0:
        return None
    value = body[separator + 4 :]
    end = value.find(b"\r\n")
    if end < 0:
        return None
    return value[:end].decode("utf-8", errors="replace")


def _replay(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _text(scope: Scope, receive: Receive, send: Send, status: int, message: str) -> None:
    response = PlainTextResponse(message, status_code=status)
    await response(scope, receive, send)


class LocalhostGuard:
    """Host, origem, cookie de sessão e CSRF do token deste processo."""

    def __init__(self, app: ASGIApp, *, token: str, port: int) -> None:
        self.app = app
        self.token = token
        self.port = port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope.get("type")
        if kind == "lifespan":
            await self.app(scope, receive, send)
            return
        if kind != "http":
            await _text(scope, receive, send, 403, _HOST_DENIED)
            return

        headers = _headers(scope)
        host = (_header_text(headers, b"host") or "").lower()
        if host not in _accepted_hosts(self.port):
            await _text(scope, receive, send, 403, _HOST_DENIED)
            return
        origin = _header_text(headers, b"origin")
        if origin is not None and origin.lower() not in _accepted_origins(self.port):
            await _text(scope, receive, send, 403, _ORIGIN_DENIED)
            return

        method = scope.get("method", "")
        method = method.upper() if isinstance(method, str) else ""
        if method == "GET" and _matches(_query_token(scope), self.token):
            response = RedirectResponse(_safe_path(scope), status_code=303)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.set_cookie(
                _COOKIE,
                self.token,
                path="/",
                httponly=True,
                samesite="strict",
                secure=False,
            )
            await response(scope, receive, send)
            return

        cookie = _cookie(_header_text(headers, b"cookie"), _COOKIE)
        if not _matches(cookie, self.token):
            await _text(scope, receive, send, 403, _COOKIE_DENIED)
            return

        if method == "POST":
            header = _header_text(headers, b"x-csrf-token")
            if not _matches(header, self.token):
                body = await _read_body(receive)
                if body is _Body.GONE:
                    return
                if body is _Body.LARGE:
                    await _text(scope, _disconnect, send, 403, _BODY_DENIED)
                    return
                field = _csrf_field(body, _header_text(headers, b"content-type"))
                if not _matches(field, self.token):
                    await _text(scope, _replay(body), send, 403, _CSRF_DENIED)
                    return
                receive = _replay(body)

        await self.app(scope, receive, send)


async def _disconnect() -> Message:
    return {"type": "http.disconnect"}
