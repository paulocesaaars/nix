"""Raiz do aplicativo e resolução de caminhos da configuração.

Caminhos relativos no TOML resolvem contra o diretório do arquivo (ou
`app_root` se ainda não houver config), nunca contra o CWD — o MCP iniciado
pelo editor costuma ter CWD do workspace, não da pasta do Nix.

`find_checkout_root` vive em `nix_launch` para o launcher achar o checkout
antes de importar o pacote `nix` (evita sombreamento da pasta do repositório).
`$NIX_HOME` (gravada pelo instalador) é o fallback quando o pacote não está
num checkout editável.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from nix_launch import find_checkout_root


def checkout_root() -> Path | None:
    """Raiz do checkout do Nix (instalação editável), ou None."""
    return find_checkout_root(Path(__file__).resolve())


def env_home() -> Path | None:
    """Pasta apontada por `$NIX_HOME`, se definida."""
    raw = os.environ.get("NIX_HOME", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    with contextlib.suppress(OSError):
        path = path.resolve()
    return path


def app_root() -> Path:
    """Pasta do aplicativo: checkout editável, senão `$NIX_HOME`, senão o CWD."""
    checkout = checkout_root()
    if checkout is not None:
        return checkout
    home = env_home()
    if home is not None:
        return home
    here = Path.cwd()
    with contextlib.suppress(OSError):
        here = here.resolve()
    return here


def default_state_dir() -> Path:
    """Estado local (índice, backups, logs): `{app_root}/.nix`."""
    return app_root() / ".nix"


def default_config_path() -> Path:
    return app_root() / "nix.toml"


def resolve_app_path(value: str, anchor: Path | None = None) -> Path:
    """Absolutos e relativos: sempre canônicos. Relativos contra a âncora."""
    path = Path(value)
    if not path.is_absolute():
        base = anchor if anchor is not None else app_root()
        path = base / path
    return path.resolve()
