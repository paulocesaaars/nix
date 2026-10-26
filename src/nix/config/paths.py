"""Raiz do aplicativo e resolução de caminhos da configuração.

Caminhos relativos resolvem contra `app_root` (a pasta da instalação), nunca
contra o CWD — o MCP iniciado pelo editor costuma ter CWD do workspace.

No checkout editável, `app_root` é a pasta do repositório, senão `$NIX_HOME`,
senão o CWD. No binário Nuitka, `__file__` aponta para a extração temporária:
a busca de checkout é ignorada e, sem `$NIX_HOME`, vale a pasta de dados da
plataforma. O CWD não entra nessa conta.

`find_checkout_root` vive em `nix_launch` para o launcher achar o checkout
antes de importar o pacote `nix` (evita sombreamento da pasta do repositório).
`$NIX_HOME` (gravada pelo instalador) é o fallback quando o pacote não está
num checkout editável.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from nix_launch import find_checkout_root


def is_packaged() -> bool:
    """True no binário Nuitka. `__compiled__` só existe no módulo compilado."""
    return "__compiled__" in globals()


def _resolve(path: Path) -> Path:
    with contextlib.suppress(OSError):
        return path.resolve()
    return path


def platform_data_dir() -> Path:
    """Pasta de dados quando o binário roda sem `$NIX_HOME`."""
    if sys.platform == "win32":
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(raw) if raw else Path.home() / "AppData" / "Local"
        return base / "nix"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "nix"
    raw = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".local" / "share"
    return base / "nix"


def platform_cache_dir() -> Path:
    """Base de `{CACHE_DIR}` do Nuitka (cache do usuário, não o diretório temporário)."""
    if sys.platform == "win32":
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        return Path(raw) if raw else Path.home() / "AppData" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    raw = os.environ.get("XDG_CACHE_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".cache"


def onefile_cache_dir(version: str) -> Path:
    """Cache da extração. Espelha `--onefile-tempdir-spec={CACHE_DIR}/nix/onefile-{VERSION}`."""
    return platform_cache_dir() / "nix" / f"onefile-{version}"


def checkout_root() -> Path | None:
    """Raiz do checkout do Nix (instalação editável), ou None."""
    if is_packaged():
        return None
    return find_checkout_root(Path(__file__).resolve())


def env_home() -> Path | None:
    """Pasta apontada por `$NIX_HOME`, se definida."""
    raw = os.environ.get("NIX_HOME", "").strip()
    if not raw:
        return None
    return _resolve(Path(raw).expanduser())


def app_root() -> Path:
    """Pasta do aplicativo.

    Checkout editável, senão `$NIX_HOME`, senão o CWD. No binário: `$NIX_HOME`
    ou a pasta de dados da plataforma.
    """
    if is_packaged():
        home = env_home()
        if home is not None:
            return home
        return _resolve(platform_data_dir())
    checkout = checkout_root()
    if checkout is not None:
        return checkout
    home = env_home()
    if home is not None:
        return home
    return _resolve(Path.cwd())


def default_state_dir() -> Path:
    """Estado local (índice, backups, logs): `{app_root}/.nix`."""
    return app_root() / ".nix"


def settings_path() -> Path:
    """Configuração persistida: `{app_root}/settings.db`."""
    return app_root() / "settings.db"


def resolve_app_path(value: str, anchor: Path | None = None) -> Path:
    """Absolutos e relativos: sempre canônicos. Relativos contra a âncora."""
    path = Path(value)
    if not path.is_absolute():
        base = anchor if anchor is not None else app_root()
        path = base / path
    return path.resolve()
