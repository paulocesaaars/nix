"""Leitores do histórico nativo. Sem leitor, o `nix run` segue com um aviso."""

from __future__ import annotations

from pathlib import Path

from nix.core.brain.history.claude import find_claude_history
from nix.core.brain.history.codex import find_codex_history


def find_previous_history(agent: str, project: Path) -> Path | None:
    """Arquivo nativo da sessão anterior, ou None se o formato não foi confirmado."""
    if agent == "claude":
        return find_claude_history(project)
    if agent == "codex":
        return find_codex_history(project)
    return None
