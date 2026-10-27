"""Escolha de agentes e raiz do projeto, compartilhada pelos comandos."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import typer

from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENTS
from nix.core.sessions.events import find_project


def choose_agents(
    requested: list[str] | None,
    *,
    command: str,
    question: Callable[[str], str],
) -> list[str]:
    """Agentes pedidos ou confirmados um a um. Nenhum vem marcado.

    `command` entra no erro quando não há terminal, por exemplo `nix hooks install`.
    `question` recebe a chave do agente e devolve o texto da confirmação.
    """
    names = [item.strip().lower() for item in (requested or []) if item.strip()]
    for name in names:
        if name not in AGENTS:
            raise ConfigError(f"Agente {name!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    if names:
        return list(dict.fromkeys(names))
    if not sys.stdin.isatty():
        raise ConfigError(
            f"Informe os agentes com `--agent`, por exemplo `{command} --agent claude --agent cursor`. "
            f"Nomes aceitos: {', '.join(AGENTS)}."
        )
    chosen = [key for key in AGENTS if typer.confirm(question(key), default=False)]
    if not chosen:
        raise ConfigError("Nenhum agente foi escolhido. Rode de novo e responda `s` para os agentes que quer ativar.")
    return chosen


def project_root(project: str | None) -> tuple[Path, str]:
    """Raiz do projeto (a pasta Git, ou a própria pasta) e a chave usada no registro."""
    key = find_project(project or "")[0]
    return Path(key), key
