"""Entrypoint Typer do comando `nix`."""

from __future__ import annotations

import contextlib
import sys

import typer

from nix import __version__
from nix.cli.commands.config_cmds import config_app
from nix.cli.commands.hooks_cmds import hooks_app
from nix.cli.commands.index_cmds import cmd_status, cmd_sync
from nix.cli.commands.session_cmds import session_app
from nix.cli.commands.setup import cmd_doctor, cmd_init
from nix.cli.commands.skills_cmds import skills_app
from nix.cli.commands.ui_cmd import cmd_ui
from nix.cli.commands.vault_cmds import vault_app
from nix.cli.render import print_banner

app = typer.Typer(
    name="nix",
    help="Servidor MCP para vaults do Obsidian. Sem subcomando, inicia o servidor stdio.",
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


@app.callback()
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", help="Mostra a versão e sai", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty():
            typer.echo(
                "Servidor MCP Nix (stdio). O cliente MCP inicia este processo; Ctrl+C encerra.",
                err=True,
            )
        from nix.mcp.server import run_server

        run_server()


app.command("init", help="Aponta o vault e grava a configuração")(cmd_init)
app.command("sync", help="Sincroniza o índice com o vault")(cmd_sync)
app.command("status", help="Mostra o estado do índice")(cmd_status)
app.command("doctor", help="Diagnóstico de ambiente, config e índice")(cmd_doctor)
app.command("ui", help="Abre a interface local de configuração e operação")(cmd_ui)
app.add_typer(config_app, name="config")
app.add_typer(vault_app, name="vault")
app.add_typer(session_app, name="session")
app.add_typer(hooks_app, name="hooks")
app.add_typer(skills_app, name="skills")


@app.command(
    "hook",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def _hook(ctx: typer.Context) -> None:
    """Chamado pelos hooks dos agentes. O `nix_launch` já atende este comando sem passar pela CLI."""
    from nix.core.sessions.hook_entry import main as hook_main

    raise typer.Exit(code=hook_main(list(ctx.args)))


@app.command("banner", hidden=True)
def _banner() -> None:
    print_banner("[bold]Nix[/bold] — servidor MCP para vaults do Obsidian.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")
    app()
