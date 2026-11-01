"""Primeira configuração: grava a wiki e o modelo no settings.db."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nix.config.editor import set_value
from nix.config.loader import clear_config_cache, load_config
from nix.config.schema import validate_wiki_name
from nix.config.store import SettingsStore
from nix.core.admin.wikis import DEFAULT_WIKI_NAME, WikiService
from nix.core.errors import ConfigError


@dataclass(frozen=True)
class InitResult:
    settings_path: Path
    wiki_name: str
    wiki_path: str
    embedding_model: str
    embedding_written: bool
    previously_initialized: bool


def initialize(
    *,
    wiki: Path,
    embedding_model: str,
    force: bool,
    update_embedding: bool,
    name: str | None = None,
) -> InitResult:
    if not wiki.is_dir():
        raise ConfigError(
            f"{wiki} não é um diretório. Aponte para a pasta raiz da wiki."
        )
    vault_text = wiki.resolve().as_posix()
    store = SettingsStore()
    mismatch = store.schema_mismatch()
    if mismatch is not None:
        if not force:
            raise mismatch
        store.recreate()
        previously = True
    else:
        previously = store.is_initialized()
    service = WikiService(store)
    embedding_written = False
    wiki_name = validate_wiki_name(name) if name else DEFAULT_WIKI_NAME
    if previously and not force:
        existing = service.list_wikis()
        if name is not None and existing:
            raise ConfigError(
                "Esta configuração já tem wikis. "
                "`nix init --name` não cria outro. Use `nix wiki add NOME CAMINHO`."
            )
        if not existing:
            service.add(wiki_name, vault_text, source="init")
        else:
            default = next((item for item in existing if item.is_default), None)
            if default is None:
                raise ConfigError("Nenhuma wiki está marcada como padrão. Use `nix wiki default NOME`.")
            service.set_path(default.name, vault_text, source="init")
        if update_embedding:
            set_value("index", "embedding_model", embedding_model, source="init", persist=True)
            embedding_written = True
    else:
        if previously and force:
            store.clear_all()
            clear_config_cache()
        service.add(wiki_name, vault_text, source="init")
        set_value("index", "embedding_model", embedding_model, source="init", persist=True)
        store.mark_initialized()
        embedding_written = True
    clear_config_cache()
    config = load_config()
    return InitResult(
        settings_path=store.path,
        wiki_name=config.default_wiki.name,
        wiki_path=config.default_wiki.path,
        embedding_model=config.index.embedding_model,
        embedding_written=embedding_written,
        previously_initialized=previously,
    )
