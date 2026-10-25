"""Entrada do binário Nuitka.

Não passa pelo launcher do checkout: esse relança o Python do `.venv`
se achar um, e o binário deixaria de ser o processo que o MCP iniciou.
"""

from __future__ import annotations


def main() -> None:
    from nix.observability.stdio import silence_progress_env

    silence_progress_env()
    from nix.cli.app import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
