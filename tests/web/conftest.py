"""Cliente HTTP da interface e o embedder que a HU-14 segura num evento."""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from tests.conftest import FakeEmbedder

from nix.core.runtime import RuntimeHost
from nix.web.jobs import RuntimeGate, SyncJobs
from nix.web.server import create_app
from nix.web.state import WebState

# Porta só do cabeçalho Host. O TestClient não abre socket; base_url e WebState.port coincidem.
_PORT = 18765
_TOKEN = "nix-test-token"


class WebClient(TestClient):
    """Sessão já aberta: cookie `nix_session` e POST com o token no campo `csrf`."""

    def __init__(self, app: Starlette, token: str, gate: RuntimeGate) -> None:
        super().__init__(app, base_url=f"http://127.0.0.1:{_PORT}")
        self.token = token
        self.gate = gate

    def post_csrf(
        self,
        url: str,
        data: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """POST com o token da sessão no campo `csrf`."""
        fields = dict(data or {})
        fields["csrf"] = self.token
        return self.post(url, data=fields, **kwargs)


def _holding_embedder(hold: threading.Event) -> type[FakeEmbedder]:
    """Subclasse do `FakeEmbedder` cujo `embed` espera o evento."""

    class HoldingEmbedder(FakeEmbedder):
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            hold.wait()
            return super().embed(texts)

    return HoldingEmbedder


@pytest.fixture
def embed_hold(monkeypatch: pytest.MonkeyPatch) -> Iterator[threading.Event]:
    """Faz o próximo `RuntimeHost` nascer com um `embed` que espera o evento.

    O `client` pede esta fixture antes de montar o host, então a sincronização
    da interface já espera. No `finally` do teste, chame `embed_hold.set()` para
    a thread terminar. A fixture também solta o evento ao encerrar.
    """
    event = threading.Event()
    monkeypatch.setattr("nix.core.runtime.Embedder", _holding_embedder(event))
    try:
        yield event
    finally:
        event.set()


@pytest.fixture
def client(
    configured: Path,
    fake_embedder: type[FakeEmbedder],
    request: pytest.FixtureRequest,
) -> Iterator[WebClient]:
    """Cliente HTTP autenticado num host novo (`FakeEmbedder`, vault configurado).

    Se o teste pede `embed_hold`, o host nasce com esse embedder. O GET
    `/?t=TOKEN` grava o cookie. O POST autenticado é `client.post_csrf`.
    """
    del fake_embedder
    hold: threading.Event | None = None
    if "embed_hold" in request.fixturenames:
        activated = request.getfixturevalue("embed_hold")
        if isinstance(activated, threading.Event):
            hold = activated
    from nix.config.loader import load_config

    host = RuntimeHost(load_config())
    state = WebState(token=_TOKEN, port=_PORT, gate=RuntimeGate(host), jobs=SyncJobs())
    app = create_app(state)
    try:
        with WebClient(app, _TOKEN, state.gate) as web:
            opened = web.get(f"/?t={_TOKEN}", follow_redirects=True)
            if opened.status_code != 200 or web.cookies.get("nix_session") != _TOKEN:
                raise RuntimeError(
                    "A sessão de teste não abriu. O GET /?t=TOKEN em "
                    f"http://127.0.0.1:{_PORT} precisa gravar o cookie nix_session e responder 200."
                )
            yield web
    finally:
        if hold is not None:
            hold.set()
        state.jobs.wait()
        host.close()
