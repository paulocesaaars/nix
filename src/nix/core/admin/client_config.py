"""Trecho de configuração MCP para cada cliente, com o caminho real do binário.

A ordem e os rótulos vêm de `AGENTS` / `AGENT_LABELS`, a mesma lista de
`agent_hooks.SPECS`. O conteúdo de cada cliente é o formato já confirmado.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from nix.core.admin.agent_hooks import SPECS
from nix.core.brain.agents import AGENT_LABELS, AGENTS
from nix.core.errors import ConfigError


@dataclass(frozen=True)
class ClientSnippet:
    key: str
    label: str
    file_hint: str
    language: str
    content: str
    notes: tuple[str, ...]


def client_snippets(command: str) -> list[ClientSnippet]:
    """`command` é o executável que sobe o servidor MCP (sem argumentos)."""
    order = tuple(spec.key for spec in SPECS)
    if order != AGENTS:
        raise ConfigError(
            "A lista de clientes do hook divergiu de AGENTS. "
            "Alinhe SPECS em agent_hooks.py com AGENTS antes de abrir Conectar cliente."
        )
    missing = [key for key in AGENTS if key not in _SNIPPETS]
    if missing:
        names = ", ".join(missing)
        raise ConfigError(
            f"Falta o snippet MCP de {names}. "
            "Acrescente o cliente em client_config.py antes de abrir Conectar cliente."
        )
    path = command.replace("\\", "/")
    return [_SNIPPETS[key](path) for key in AGENTS]


def _cursor(path: str) -> ClientSnippet:
    return ClientSnippet(
        key="cursor",
        label=AGENT_LABELS["cursor"],
        file_hint=".cursor/mcp.json (projeto) ou ~/.cursor/mcp.json (global)",
        language="json",
        content=_json({"mcpServers": {"nix": {"command": path}}}),
        notes=("Depois de salvar, ative o servidor nix em Settings → MCP.",),
    )


def _copilot(path: str) -> ClientSnippet:
    return ClientSnippet(
        key="copilot",
        label=AGENT_LABELS["copilot"],
        file_hint=".vscode/mcp.json",
        language="json",
        content=_json({"servers": {"nix": {"type": "stdio", "command": path}}}),
        notes=("Abra o Chat no modo Agent e confira as ferramentas do nix em Tools.",),
    )


def _claude(path: str) -> ClientSnippet:
    return ClientSnippet(
        key="claude",
        label=AGENT_LABELS["claude"],
        file_hint="terminal, em qualquer pasta (escopo do usuário)",
        language="shell",
        content=f'claude mcp add nix --scope user -- "{path}"',
        notes=(
            "Rode claude mcp list para conferir se o nix aparece conectado.",
            "Prefere arquivo? Use .mcp.json com o mesmo bloco mcpServers do Cursor.",
        ),
    )


def _codex(path: str) -> ClientSnippet:
    return ClientSnippet(
        key="codex",
        label=AGENT_LABELS["codex"],
        file_hint="~/.codex/config.toml",
        language="toml",
        content=f"[mcp_servers.nix]\ncommand = {_toml_string(path)}\n",
        notes=("Cole este bloco em ~/.codex/config.toml. O valor de command é o caminho absoluto.",),
    )


_SNIPPETS: dict[str, Callable[[str], ClientSnippet]] = {
    "cursor": _cursor,
    "copilot": _copilot,
    "claude": _claude,
    "codex": _codex,
}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
