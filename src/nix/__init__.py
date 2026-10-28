"""Nix — servidor MCP para vaults do Obsidian."""

from typing import Any


def __getattr__(name: str) -> Any:
    """`__version__` sai do metadata só quando alguém pede.

    O hook de sessão importa `nix` a cada evento e não paga o custo do metadata.
    A versão da release (`pyproject.toml`) é a fonte da verdade: num checkout do
    código-fonte ela vence o metadata, que fica velho numa instalação editável.
    """
    if name == "__version__":
        found = _checkout_version()
        if found is None:
            from importlib.metadata import PackageNotFoundError, version

            try:
                found = version("nix")
            except PackageNotFoundError:  # fora de um checkout e sem instalação
                found = "0.0.0+dev"
        globals()["__version__"] = found
        return found
    raise AttributeError(f"module 'nix' has no attribute {name!r}")


def _checkout_version() -> str | None:
    """Lê a versão do `pyproject.toml` quando `nix` roda de um checkout (`src/nix`)."""
    from pathlib import Path

    package = Path(__file__).resolve().parent
    if package.parent.name != "src":
        return None
    pyproject = package.parent.parent / "pyproject.toml"
    try:
        import tomllib

        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    except (OSError, ValueError):
        return None
    found = project.get("version")
    return found if project.get("name") == "nix" and isinstance(found, str) else None
