"""Cenário de `bdd/` do tráfego MCP na interface: HU-08.9."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from tests.web.conftest import WebClient

from nix.config.loader import load_config
from nix.mcp.traffic import install_traffic_logging

_QUERY = "consulta-secreta-hu089"
_CLIENT = "Agente Teste 9.9"
_DURATION = re.compile(r"\d+ ms")


class _Chain:
    """Cadeia mínima com `append`, o contrato que o servidor MCP expõe."""

    def __init__(self) -> None:
        self.items: list[Any] = []

    def append(self, item: Any) -> None:
        self.items.append(item)


class _Server:
    def __init__(self) -> None:
        self.middleware = _Chain()


class _Call:
    def __init__(self, method: str, params: dict[str, object]) -> None:
        self.method = method
        self.params = params


class _Ok:
    isError = False


async def _call_next(_ctx: _Call) -> _Ok:
    return _Ok()


@pytest.mark.bdd("HU-08.9")
def test_traffic_page_hides_query_when_prompts_are_off(client: WebClient) -> None:
    # O mesmo encaixe do servidor: initialize e tools/call passam pelo middleware.
    server = _Server()
    install_traffic_logging(server, log_prompts=load_config().logging.log_prompts)
    assert server.middleware.items, "O servidor de teste não recebeu o middleware de tráfego."
    logger = server.middleware.items[0]

    async def drive() -> None:
        await logger(
            _Call("initialize", {"clientInfo": {"name": "Agente Teste", "version": "9.9"}}),
            _call_next,
        )
        await logger(
            _Call("tools/call", {"name": "search_notes", "arguments": {"query": _QUERY}}),
            _call_next,
        )

    asyncio.run(drive())

    page = client.get("/traffic")
    assert page.status_code == 200
    html = page.text
    assert _CLIENT in html
    assert "search_notes" in html
    assert _DURATION.search(html)
    assert 'class="badge b-ok">ok</span>' in html
    assert _QUERY not in html
