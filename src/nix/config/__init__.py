"""Configuração validada do Nix.

Os nomes públicos carregam sob demanda: importar `nix.config.paths` (caso do
hook de sessão) não puxa o Pydantic nem o schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nix.config.loader import clear_config_cache, load_config, require_initialized
    from nix.config.schema import NixConfig

__all__ = [
    "NixConfig",
    "clear_config_cache",
    "load_config",
    "require_initialized",
]


def __getattr__(name: str) -> Any:
    if name == "NixConfig":
        from nix.config.schema import NixConfig

        return NixConfig
    if name in {"clear_config_cache", "load_config", "require_initialized"}:
        from nix.config import loader

        return getattr(loader, name)
    raise AttributeError(f"module 'nix.config' has no attribute {name!r}")
