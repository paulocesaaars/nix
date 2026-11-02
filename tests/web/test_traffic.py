"""Cenários de `bdd/` do tráfego MCP na interface: HU-08.9 e HU-08.20."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from tests.web.conftest import WebClient

from nix.config.loader import clear_config_cache, load_config
from nix.config.store import SettingsStore
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


class _Err:
    isError = True


async def _call_next(_ctx: _Call) -> _Ok:
    return _Ok()


async def _call_error(_ctx: _Call) -> _Err:
    return _Err()


async def _call_raises(_ctx: _Call) -> _Ok:
    raise RuntimeError("ferramenta falhou")


def _middleware() -> Any:
    server = _Server()
    install_traffic_logging(server, log_prompts=False)
    assert server.middleware.items, "O servidor de teste não recebeu o middleware de tráfego."
    return server.middleware.items[0]


def _tool_call() -> _Call:
    return _Call("tools/call", {"name": "search_notes", "arguments": {}})


def _reset_editor_mark() -> None:
    SettingsStore().write_many([("ui", "editor_called", False)], source="test", record_history=False)
    clear_config_cache()


def _mark_history_rows() -> int:
    with SettingsStore().transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM settings_history WHERE section = ? AND key = ?",
            ("ui", "editor_called"),
        ).fetchone()
    assert row is not None
    return int(row[0])


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


@pytest.mark.bdd("HU-08.20")
def test_first_tool_call_saves_the_editor_mark_on_success_and_error(
    configured: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del configured
    logger = _middleware()
    call = _tool_call()

    asyncio.run(logger(call, _call_next))
    assert load_config().ui.editor_called is True
    assert _mark_history_rows() == 0

    _reset_editor_mark()
    failed = asyncio.run(logger(call, _call_error))
    assert failed.isError is True
    assert load_config().ui.editor_called is True
    assert _mark_history_rows() == 0

    _reset_editor_mark()
    with pytest.raises(RuntimeError, match="ferramenta falhou"):
        asyncio.run(logger(call, _call_raises))
    assert load_config().ui.editor_called is True
    assert _mark_history_rows() == 0

    _reset_editor_mark()

    def _broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("não foi possível gravar a marca")

    monkeypatch.setattr("nix.mcp.traffic.mark_editor_called", _broken)
    result = asyncio.run(logger(call, _call_next))
    assert isinstance(result, _Ok)
    clear_config_cache()
    assert load_config().ui.editor_called is False
