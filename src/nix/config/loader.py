"""Carregamento da configuração: ambiente > settings.db > padrão."""

from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from nix.config.paths import app_root, settings_path
from nix.config.schema import NixConfig, iter_config_fields
from nix.config.store import SettingsStore
from nix.core.errors import ConfigError

_cached: NixConfig | None = None


def require_initialized() -> SettingsStore:
    """Falha com ação corretiva quando `nix init` ainda não rodou."""
    store = SettingsStore()
    mismatch = store.schema_mismatch()
    if mismatch is not None:
        raise mismatch
    if not store.is_initialized():
        raise ConfigError(
            f"O Nix ainda não foi configurado ({store.path}). Rode `nix init` para cadastrar o vault."
        )
    return store


def env_defines(section: str, key: str) -> bool:
    table = env_overrides().get(section)
    return isinstance(table, dict) and key in table


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def env_overrides() -> dict[str, Any]:
    """Lê NIX_SECTION__FIELD dos campos globais. O ambiente ganha do settings.db.

    Vaults ficam na tabela `vaults`. `NIX_VAULT__*` não entra nessa precedência.
    """
    nested: dict[str, dict[str, Any]] = {}
    prefix = "NIX_"
    for raw_key, raw_value in os.environ.items():
        if not raw_key.startswith(prefix):
            continue
        rest = raw_key[len(prefix) :]
        if "__" not in rest:
            continue
        section, field = rest.split("__", 1)
        nested.setdefault(section.lower(), {})[field.lower()] = _coerce_env(raw_value)
    return nested


def _coerce_env(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _format_validation(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err["loc"])
        parts.append(f"{loc}: {err['msg']}")
    joined = "; ".join(parts)
    return (
        f"Configuração inválida ({joined}). Corrija com `nix config set` "
        "ou remova a variável NIX_* correspondente."
    )


def _sources(db: dict[str, dict[str, Any]], env: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for field in iter_config_fields():
        env_table = env.get(field.section)
        db_table = db.get(field.section)
        if isinstance(env_table, dict) and field.key in env_table:
            found[field.dotted] = "env"
        elif isinstance(db_table, dict) and field.key in db_table:
            found[field.dotted] = "db"
        else:
            found[field.dotted] = "default"
    return found


def config_document(store: SettingsStore) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """`(db, env, merged)` com os vaults da tabela.

    A seção `vault` antiga e `NIX_VAULT__*` ficam de fora: o cadastro vive em `vaults`.
    """
    db = store.load_overrides()
    db.pop("vault", None)
    env = env_overrides()
    env.pop("vault", None)
    merged = deep_merge(db, env)
    merged.pop("vault", None)
    merged["vaults"] = [record.payload() for record in store.list_vaults()]
    return db, env, merged


def load_config(*, use_cache: bool = True) -> NixConfig:
    """Carrega e valida a configuração. Precedência: ambiente > settings.db > padrão."""
    global _cached
    if use_cache and _cached is not None:
        return _cached

    store = SettingsStore()
    db, env, merged = config_document(store)
    try:
        config = NixConfig.model_validate(merged, context={"path_anchor": app_root()})
    except ValidationError as exc:
        raise ConfigError(_format_validation(exc)) from exc
    except ConfigError:
        raise

    config.settings_path = settings_path()
    config.sources = _sources(db, env)
    if use_cache:
        _cached = config
    return config


def clear_config_cache() -> None:
    global _cached
    _cached = None


def public_dict(config: NixConfig) -> dict[str, Any]:
    """Serializa a config para exibição."""
    return config.model_dump(mode="json")
