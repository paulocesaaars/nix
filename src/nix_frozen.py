"""Entrada do binário Nuitka.

Não passa pelo launcher do checkout: esse relança o Python do `.venv`
se achar um, e o binário deixaria de ser o processo que o MCP iniciou.
"""

from __future__ import annotations


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        # `nix hook` não passa pela CLI: só a biblioteca padrão e `core/sessions` (RF-130, meta de 300 ms).
        from nix.core.sessions.hook_entry import main as hook_main

        raise SystemExit(hook_main(sys.argv[2:]))

    from nix.observability.stdio import silence_progress_env

    silence_progress_env()
    from nix.cli.app import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
