"""Nix — servidor MCP para vaults do Obsidian."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nix")
except PackageNotFoundError:  # código-fonte executado sem `pip install -e .`
    __version__ = "0.0.0+dev"
