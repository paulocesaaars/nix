"""Permite `python -m nix` pelo pacote instalado."""

from __future__ import annotations

try:
    from nix_launch import main
except ImportError:
    from nix.cli.app import main

if __name__ == "__main__":
    main()
