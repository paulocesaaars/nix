"""Servidor local da interface."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import socket
import sys
import webbrowser

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware

from nix.config.loader import load_config
from nix.core.errors import NixError
from nix.core.runtime import RuntimeHost
from nix.web.jobs import RuntimeGate, SyncJobs
from nix.web.routes import build_routes
from nix.web.security import LocalhostGuard
from nix.web.state import WebState


def create_app(state: WebState) -> Starlette:
    app = Starlette(
        routes=build_routes(),
        middleware=[Middleware(LocalhostGuard, token=state.token, port=state.port)],
    )
    app.state.web = state
    return app


def serve(*, port: int | None, open_browser: bool) -> None:
    """Sobe a interface em 127.0.0.1 e bloqueia até Ctrl+C ou o botão Encerrar."""
    listener = _listen(port)
    host: RuntimeHost | None = None
    state: WebState | None = None
    try:
        chosen = int(listener.getsockname()[1])
        token = secrets.token_urlsafe(32)
        host = RuntimeHost(load_config())
        state = WebState(token=token, port=chosen, gate=RuntimeGate(host), jobs=SyncJobs())
        app = create_app(state)
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=chosen,
            loop="asyncio",
            http="h11",
            log_config=None,
            access_log=False,
            timeout_graceful_shutdown=2,
        )
        server = uvicorn.Server(config)
        state.server = server
        asyncio.run(_run(server, listener, chosen, token, open_browser))
    finally:
        try:
            if state is not None:
                state.jobs.wait()
        finally:
            if host is not None:
                host.close()
            with contextlib.suppress(OSError):
                listener.close()


def _listen(port: int | None) -> socket.socket:
    """Reserva a porta sem SO_REUSEADDR, para falhar se outra escuta já existir."""
    if port is not None and (port < 1 or port > 65535):
        raise NixError(f"Porta {port} inválida. Use um número entre 1 e 65535, ou omita --port.")
    number = 0 if port is None else port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", number))
        sock.listen(2048)
        sock.set_inheritable(True)
    except OSError as exc:
        sock.close()
        label = str(number) if number else "automática"
        detail = exc.strerror or str(exc)
        raise NixError(
            f"A porta {label} não está livre ({detail}). Escolha outra com `nix ui --port` ou omita --port."
        ) from exc
    return sock


async def _run(
    server: uvicorn.Server,
    listener: socket.socket,
    port: int,
    token: str,
    open_browser: bool,
) -> None:
    async def announce() -> None:
        while not server.started and not server.should_exit:
            await asyncio.sleep(0.02)
        if not server.started:
            return
        url = f"http://127.0.0.1:{port}/?t={token}"
        print(url, flush=True)
        if not open_browser:
            return
        opened = await asyncio.to_thread(webbrowser.open, url)
        if not opened:
            print("Não foi possível abrir o navegador. Abra a URL acima.", file=sys.stderr, flush=True)

    announcer = asyncio.create_task(announce())
    try:
        await server.serve(sockets=[listener])
    finally:
        announcer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await announcer
