"""Pastas que a Nix esvazia e pode apagar, sem sair da raiz do projeto."""

from __future__ import annotations

from pathlib import Path


def prune_empty_dirs(directory: Path, root: Path) -> None:
    """Sobe apagando pastas vazias. Para na raiz do projeto."""
    current = directory
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
