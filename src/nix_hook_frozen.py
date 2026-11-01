"""Entrada do binário leve `nix-hook`.

Não carrega CLI, Pydantic nem o índice. O agente chama
`nix-hook brain --event E --agent A`. O subcomando antigo `hook` sai em
silêncio para não quebrar uma instalação que ainda não foi reinstalada.
"""

from __future__ import annotations


def main() -> None:
    import sys

    args = sys.argv[1:]
    if not args or args[0] != "brain":
        raise SystemExit(0)
    from nix.core.brain.hook_entry import main as hook_main

    raise SystemExit(hook_main(args[1:]))


if __name__ == "__main__":
    main()
