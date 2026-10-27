"""Entrada do binário leve `nix-hook`.

Não carrega CLI, Pydantic nem o índice. O agente chama
`nix-hook hook --event E --agent A`; o primeiro argumento `hook` é a mesma
marca do `nix hook` de desenvolvimento.
"""

from __future__ import annotations


def main() -> None:
    import sys

    args = sys.argv[1:]
    if args and args[0] == "hook":
        args = args[1:]
    from nix.core.sessions.hook_entry import main as hook_main

    raise SystemExit(hook_main(args))


if __name__ == "__main__":
    main()
