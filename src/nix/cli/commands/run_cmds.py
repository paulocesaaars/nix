"""nix run <agente>."""

from __future__ import annotations

import typer

from nix.cli.deps import with_errors
from nix.core.brain.agents import AGENTS
from nix.core.brain.run import launch


def cmd_run(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help=f"Agente ({', '.join(AGENTS)})."),
    no_autowire: bool = typer.Option(False, "--no-autowire", help="Não instala hook nem MCP."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    """Sobe o agente. A cópia do histórico some quando ele termina."""
    raise typer.Exit(code=_launch(ctx, agent, no_autowire=no_autowire, project=project))


@with_errors
def _launch(ctx: typer.Context, agent: str, *, no_autowire: bool, project: str | None) -> int:
    return launch(agent, list(ctx.args), project=project, autowire=not no_autowire)
