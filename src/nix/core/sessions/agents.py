"""Agentes suportados e o formato do contexto que cada um aceita no início da sessão.

Ponto único da lista de agentes (só biblioteca padrão: o hook importa este módulo).
Um agente novo entra aqui, em `core/admin/agent_hooks.SPECS` e em
`core/admin/agent_skills.DESTINATIONS`.
"""

from __future__ import annotations

import json
from collections.abc import Callable

AGENT_LABELS: dict[str, str] = {
    "claude": "Claude Code",
    "cursor": "Cursor",
    "copilot": "Copilot",
    "devin": "Devin CLI",
    "devin-desktop": "Devin Desktop",
}
AGENTS: tuple[str, ...] = tuple(AGENT_LABELS)


def _cursor(text: str) -> dict[str, object]:
    return {"additional_context": text}


def _hook_specific(text: str) -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _copilot(text: str) -> dict[str, object]:
    return {"additionalContext": text}


# Devin Desktop não tem evento de início de sessão nem injeta o stdout na conversa: fica de fora.
_CONTEXT_FORMATS: dict[str, Callable[[str], dict[str, object]]] = {
    "cursor": _cursor,
    "claude": _hook_specific,
    "devin": _hook_specific,
    "copilot": _copilot,
}


def context_output(agent: str, text: str) -> str:
    """Saída do hook de início de sessão no formato do agente, ou vazio se ele não lê stdout."""
    build = _CONTEXT_FORMATS.get(agent)
    return json.dumps(build(text), ensure_ascii=False) if build else ""
