"""Configuração validada do Nix."""

from nix.config.loader import clear_config_cache, load_config, require_initialized
from nix.config.schema import NixConfig

__all__ = [
    "NixConfig",
    "clear_config_cache",
    "load_config",
    "require_initialized",
]
