"""Comando `nix ui`."""

from __future__ import annotations

import typer

from nix.cli.deps import with_errors
from nix.config.loader import require_initialized
from nix.web.server import serve


def open_interface() -> None:
    """Abre a interface. Não exige a wiki cadastrada."""
    serve(port=None, open_browser=True)


@with_errors
def cmd_ui(
    no_browser: bool = typer.Option(False, "--no-browser", help="Não abre o navegador, só imprime a URL"),
    port: int | None = typer.Option(None, "--port", help="Porta. Omitida, usa uma porta livre"),
) -> None:
    """Abre a interface local de configuração e operação."""
    require_initialized()
    serve(port=port, open_browser=not no_browser)
