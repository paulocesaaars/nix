"""Configuração validada do Nix."""

from nix.config.loader import clear_config_cache, config_write_path, load_config, resolve_config_path
from nix.config.schema import NixConfig

__all__ = [
    "NixConfig",
    "clear_config_cache",
    "config_write_path",
    "load_config",
    "resolve_config_path",
]
