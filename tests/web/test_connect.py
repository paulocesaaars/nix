"""Cenários de `bdd/` da página Conectar cliente: HU-08.11 e HU-08.12."""

from __future__ import annotations

import re

import pytest
from tests.web.conftest import WebClient

from nix.core.brain.agents import AGENTS

_COMMAND = "C:/Ferramentas/nix.exe"
_TAB_ORDER = ("Cursor", "VS Code", "Claude Code", "Codex")
_REMOVED = ("Gemini", "OpenCode", "Kimi", "Kiro", "Grok", "Antigravity", "Devin Desktop", "Devin CLI")


def _page(client: WebClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(
        "nix.web.routes.integration.nix_command",
        lambda: (_COMMAND, None),
    )
    response = client.get("/connect")
    assert response.status_code == 200
    return response.text


@pytest.mark.bdd("HU-08.11")
def test_connect_page_lists_clients_in_order(client: WebClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = _page(client, monkeypatch)
    labels = re.findall(r'role="tab"[^>]*>([^<]*)</button>', html)
    assert labels == list(_TAB_ORDER)
    assert re.findall(r'id="tab-([^"]+)"', html) == list(AGENTS)
    for name in _REMOVED:
        assert name not in html

    start = html.find('id="panel-codex"')
    assert start >= 0
    panel = html[start : html.find('id="panel-', start + 1)]
    assert "[mcp_servers.nix]" in panel
    assert _COMMAND in panel
    assert "~/.codex/config.toml" in panel
    assert "codex mcp" not in panel.lower()


@pytest.mark.bdd("HU-08.12")
def test_connect_page_explains_hooks_without_writing(client: WebClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = _page(client, monkeypatch)
    start = html.find('id="hooks"')
    assert start >= 0
    section = html[start:]
    assert f"um, alguns ou todos os {len(AGENTS)} clientes" in section
    assert "global ou só o repositório" in section
    assert "nix brain hooks install" in section
    assert "nix hooks install" not in section
    assert "Esta página não grava arquivo" in section
