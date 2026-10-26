"""Primeira configuração: grava o vault e o modelo no settings.db."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nix.config.editor import set_value
from nix.config.loader import clear_config_cache, load_config
from nix.config.store import SettingsStore
from nix.core.errors import ConfigError


@dataclass(frozen=True)
class InitResult:
    settings_path: Path
    vault_path: str
    embedding_model: str
    embedding_written: bool
    previously_initialized: bool


def initialize(
    *,
    vault: Path,
    embedding_model: str,
    force: bool,
    update_embedding: bool,
) -> InitResult:
    if not vault.is_dir():
        raise ConfigError(
            f"{vault} não é um diretório. Aponte para a pasta raiz do vault do Obsidian."
        )
    vault_text = vault.resolve().as_posix()
    store = SettingsStore()
    previously = store.is_initialized()
    embedding_written = False
    if previously and not force:
        set_value("vault", "path", vault_text, source="init", persist=True)
        if update_embedding:
            set_value("index", "embedding_model", embedding_model, source="init", persist=True)
            embedding_written = True
    else:
        if previously and force:
            store.clear_all()
            clear_config_cache()
        set_value("vault", "path", vault_text, source="init", persist=True)
        set_value("index", "embedding_model", embedding_model, source="init", persist=True)
        store.mark_initialized()
        embedding_written = True
    clear_config_cache()
    config = load_config()
    return InitResult(
        settings_path=store.path,
        vault_path=config.vault.path,
        embedding_model=config.index.embedding_model,
        embedding_written=embedding_written,
        previously_initialized=previously,
    )
