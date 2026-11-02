"""Cenários de `bdd/` da página Conectar cliente: HU-08.11 e HU-08.12."""

from __future__ import annotations

import re

import pytest
from tests.web.conftest import WebClient

from nix.core.brain.agents import AGENTS

_COMMAND = "C:/Ferramentas/nix.exe"
_TAB_ORDER = (
    "Cursor",
    "VS Code",
    "Claude Code",
    "Codex",
    "Command Code",
    "Devin (CLI e Desktop)",
    "OpenCode",
    "Gemini CLI",
    "Oh My Pi",
    "Pi",
    "OpenClaw",
    "Antigravity CLI",
    "Grok Build CLI",
    "Zero",
    "ZCode",
    "Kimi Code",
    "Kiro CLI",
    "GitHub Copilot CLI",
    "Factory Droid",
    "Meta Muse Code",
    "IBM Bob",
    "Qwen Code",
    "Qoder",
    "Hermes Agent",
)


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
    panel = _panel(html, "codex")
    assert "[mcp_servers.nix]" in panel
    assert _COMMAND in panel
    assert "~/.codex/config.toml" in panel
    assert "codex mcp" not in panel.lower()

    devin = _panel(html, "devin")
    assert "mcpServers" in devin
    assert _COMMAND in devin


def _panel(html: str, key: str) -> str:
    start = html.find(f'id="panel-{key}"')
    assert start >= 0
    end = html.find('id="panel-', start + 1)
    return html[start:] if end < 0 else html[start:end]


@pytest.mark.bdd("HU-08.22")
def test_snippets_use_the_local_command_and_no_url(client: WebClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = _page(client, monkeypatch)
    for key in AGENTS:
        panel = _panel(html, key)
        assert _COMMAND in panel, key
        assert "http://" not in panel and "https://" not in panel, key


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
