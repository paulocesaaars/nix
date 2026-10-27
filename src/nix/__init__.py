"""Nix — servidor MCP para vaults do Obsidian."""

from typing import Any


def __getattr__(name: str) -> Any:
    """`__version__` sai do metadata só quando alguém pede.

    O hook de sessão importa `nix` a cada evento e não paga o custo do metadata.
    """
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            found = version("nix")
        except PackageNotFoundError:  # código-fonte executado sem `pip install -e .`
            found = "0.0.0+dev"
        globals()["__version__"] = found
        return found
    raise AttributeError(f"module 'nix' has no attribute {name!r}")
