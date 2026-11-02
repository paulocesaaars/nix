"""Agentes suportados e o formato do contexto que cada um aceita no início da sessão.

Ponto único da lista de agentes (só biblioteca padrão: o hook importa este módulo).
Um agente novo entra aqui, em `core/admin/agent_hooks.SPECS` e no snippet de `client_config`.
A ordem é a de `nix brain hooks install --all`.
"""

from __future__ import annotations

import json
from collections.abc import Callable

AGENT_LABELS: dict[str, str] = {
    "cursor": "Cursor",
    "copilot": "VS Code",
    "claude": "Claude Code",
    "codex": "Codex",
    "command-code": "Command Code",
    "devin": "Devin (CLI e Desktop)",
    "opencode": "OpenCode",
    "gemini": "Gemini CLI",
    "omp": "Oh My Pi",
    "pi": "Pi",
    "openclaw": "OpenClaw",
    "antigravity": "Antigravity CLI",
    "grok": "Grok Build CLI",
    "zero": "Zero",
    "zcode": "ZCode",
    "kimi": "Kimi Code",
    "kiro": "Kiro CLI",
    "copilot-cli": "GitHub Copilot CLI",
    "droid": "Factory Droid",
    "muse": "Meta Muse Code",
    "ibm-bob": "IBM Bob",
    "qwen": "Qwen Code",
    "qoder": "Qoder",
    "hermes": "Hermes Agent",
}
AGENTS: tuple[str, ...] = tuple(AGENT_LABELS)

# Binário chamado por `nix run` quando difere da chave. `copilot` é o VS Code; o CLI é o binário `copilot`.
EXECUTABLES: dict[str, str] = {
    "command-code": "cmd",
    "antigravity": "agy",
    "kiro": "kiro-cli",
    "copilot-cli": "copilot",
    "ibm-bob": "bob",
    "qoder": "qodercli",
}


def executable_for(agent: str) -> str:
    return EXECUTABLES.get(agent, agent)


def _cursor(text: str) -> dict[str, object]:
    return {"additional_context": text}


def _hook_specific(text: str) -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _copilot(text: str) -> dict[str, object]:
    return {"additionalContext": text}


_CONTEXT_FORMATS: dict[str, Callable[[str], dict[str, object]]] = {
    "cursor": _cursor,
    "claude": _hook_specific,
    "copilot": _copilot,
}


# Codex: a documentação confirma que o stdout em texto puro vira contexto do modelo.
_PLAIN_CONTEXT = frozenset({"codex"})


def context_output(agent: str, text: str) -> str:
    """Saída do hook de início de sessão no formato do agente, ou vazio se ele não lê stdout."""
    if agent in _PLAIN_CONTEXT:
        return text
    build = _CONTEXT_FORMATS.get(agent)
    return json.dumps(build(text), ensure_ascii=False) if build else ""
