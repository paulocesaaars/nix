"""Trecho de configuração MCP para cada cliente, com o caminho real do binário."""

from __future__ import annotations

import json
from dataclasses import dataclass


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
    path = command.replace("\\", "/")
    return [
        ClientSnippet(
            key="cursor",
            label="Cursor",
            file_hint=".cursor/mcp.json (projeto) ou ~/.cursor/mcp.json (global)",
            language="json",
            content=_json({"mcpServers": {"nix": {"command": path}}}),
            notes=("Depois de salvar, ative o servidor nix em Settings → MCP.",),
        ),
        ClientSnippet(
            key="claude-code",
            label="Claude Code",
            file_hint="terminal, em qualquer pasta (escopo do usuário)",
            language="shell",
            content=f'claude mcp add nix --scope user -- "{path}"',
            notes=(
                "Rode claude mcp list para conferir se o nix aparece conectado.",
                "Prefere arquivo? Use .mcp.json com o mesmo bloco mcpServers do Cursor.",
            ),
        ),
        ClientSnippet(
            key="vscode",
            label="VS Code · Copilot",
            file_hint=".vscode/mcp.json",
            language="json",
            content=_json({"servers": {"nix": {"type": "stdio", "command": path}}}),
            notes=("Abra o Chat no modo Agent e confira as ferramentas do nix em Tools.",),
        ),
    ]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
