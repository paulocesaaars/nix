"""Entrypoint Typer do comando `nix`."""

from __future__ import annotations

import contextlib
import sys

import typer

from nix import __version__
from nix.cli.commands.brain_cmds import brain_app
from nix.cli.commands.config_cmds import config_app
from nix.cli.commands.index_cmds import cmd_status, cmd_sync
from nix.cli.commands.run_cmds import cmd_run
from nix.cli.commands.setup import cmd_doctor, cmd_init
from nix.cli.commands.ui_cmd import cmd_ui
from nix.cli.commands.wiki_cmds import wiki_app
from nix.cli.render import print_banner

app = typer.Typer(
    name="nix",
    help="Wikis de notas para agentes. No terminal, sem subcomando, abre a interface.",
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
        # Terminal: a pessoa digitou `nix`. O cliente MCP não tem TTY e segue no stdio.
        if sys.stdin is not None and sys.stdin.isatty():
            from nix.cli.commands.ui_cmd import open_interface
            from nix.cli.render import print_error
            from nix.core.errors import NixError

            try:
                open_interface()
            except NixError as exc:
                print_error(exc.message)
                raise typer.Exit(code=1) from exc
            return
        from nix.mcp.server import run_server

        run_server()


app.command("init", help="Aponta a wiki e grava a configuração")(cmd_init)
app.command("sync", help="Sincroniza o índice com a wiki")(cmd_sync)
app.command("status", help="Mostra o estado do índice")(cmd_status)
app.command("doctor", help="Diagnóstico de ambiente, config e índice")(cmd_doctor)
app.command("ui", help="Abre a interface local de configuração e operação")(cmd_ui)
app.add_typer(config_app, name="config")
app.add_typer(wiki_app, name="wiki")
app.add_typer(brain_app, name="brain")
app.command(
    "run",
    help="Sobe um agente com hook, MCP e o histórico da sessão anterior",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(cmd_run)


@app.command(
    "hook",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def _hook(ctx: typer.Context) -> None:
    """Subcomando antigo. Não grava nada, para instalações anteriores não quebrarem."""
    del ctx
    raise typer.Exit(code=0)


@app.command("banner", hidden=True)
def _banner() -> None:
    print_banner("[bold]Nix[/bold] — servidor MCP para wikis de notas.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")
    app()
