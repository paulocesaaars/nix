"""Primeira configuração: grava o vault e o modelo no settings.db."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nix.config.editor import set_value
from nix.config.loader import clear_config_cache, load_config
from nix.config.schema import validate_vault_name
from nix.config.store import SettingsStore
from nix.core.admin.vaults import DEFAULT_VAULT_NAME, VaultService
from nix.core.errors import ConfigError


@dataclass(frozen=True)
class InitResult:
    settings_path: Path
    vault_name: str
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
    name: str | None = None,
) -> InitResult:
    if not vault.is_dir():
        raise ConfigError(
            f"{vault} não é um diretório. Aponte para a pasta raiz do vault do Obsidian."
        )
    vault_text = vault.resolve().as_posix()
    store = SettingsStore()
    mismatch = store.schema_mismatch()
    if mismatch is not None:
        if not force:
            raise mismatch
        store.recreate()
        previously = True
    else:
        previously = store.is_initialized()
    service = VaultService(store)
    embedding_written = False
    vault_name = validate_vault_name(name) if name else DEFAULT_VAULT_NAME
    if previously and not force:
        existing = service.list_vaults()
        if name is not None and existing:
            raise ConfigError(
                "Esta configuração já tem vaults. "
                "`nix init --name` não cria outro. Use `nix vault add NOME CAMINHO`."
            )
        if not existing:
            service.add(vault_name, vault_text, source="init")
        else:
            default = next((item for item in existing if item.is_default), None)
            if default is None:
                raise ConfigError("Nenhum vault está marcado como padrão. Use `nix vault default NOME`.")
            service.set_path(default.name, vault_text, source="init")
        if update_embedding:
            set_value("index", "embedding_model", embedding_model, source="init", persist=True)
            embedding_written = True
    else:
        if previously and force:
            store.clear_all()
            clear_config_cache()
        service.add(vault_name, vault_text, source="init")
        set_value("index", "embedding_model", embedding_model, source="init", persist=True)
        store.mark_initialized()
        embedding_written = True
    clear_config_cache()
    config = load_config()
    return InitResult(
        settings_path=store.path,
        vault_name=config.default_vault.name,
        vault_path=config.default_vault.path,
        embedding_model=config.index.embedding_model,
        embedding_written=embedding_written,
        previously_initialized=previously,
    )
