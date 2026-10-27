"""Gravação validada da configuração no settings.db."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from nix.config.loader import (
    clear_config_cache,
    config_document,
    deep_merge,
    env_defines,
    load_config,
)
from nix.config.paths import app_root
from nix.config.schema import VAULT_SETTING_KEYS, ConfigField, NixConfig, config_field, iter_config_fields
from nix.config.store import VAULTS_SECTION, SettingsChange, SettingsStore
from nix.core.errors import ConfigError

Source = str


@dataclass(frozen=True)
class SetResult:
    dotted: str
    changed: bool
    warning: str | None


@dataclass(frozen=True)
class BatchResult:
    changed: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ConfigEntry:
    section: str
    key: str
    dotted: str
    value: Any
    source: str
    description: str
    editable: bool
    widget: str
    choices: tuple[str, ...] | None
    ge: float | None
    le: float | None
    warning: str | None
    env_name: str


def split_key(dotted: str) -> tuple[str, str]:
    if "." not in dotted:
        raise ConfigError(
            f"Campo {dotted!r} precisa ser secao.chave, por exemplo logging.level. Rode `nix config list`."
        )
    section, key = dotted.split(".", 1)
    return section, key


def require_field(section: str, key: str) -> ConfigField:
    if section == "vault":
        raise ConfigError(_vault_field_message(key))
    try:
        return config_field(section, key)
    except KeyError:
        raise ConfigError(
            f"Campo {section}.{key} não existe. Rode `nix config list` para ver os campos."
        ) from None


def _vault_field_message(key: str) -> str:
    if key == "path":
        return (
            "vault.path não é um campo da configuração global. "
            "Troque a pasta com `nix vault path NOME CAMINHO`."
        )
    if key == "legacy_layout":
        return (
            "legacy_layout é gravado na migração do settings.db e não se edita. "
            "O índice e os backups desse vault continuam na pasta de origem."
        )
    if key == "name":
        return "O nome do vault muda com `nix vault rename ANTIGO NOVO`."
    if key == "is_default":
        return "O vault padrão muda com `nix vault default NOME`."
    if key in VAULT_SETTING_KEYS:
        return (
            f"vault.{key} é um ajuste de um vault, não da configuração global. "
            f"Rode `nix vault set NOME {key} VALOR`."
        )
    return (
        f"Campo vault.{key} não existe. Os vaults não se editam com `nix config set`. "
        "Rode `nix vault list`."
    )


def snapshot() -> list[ConfigEntry]:
    config = load_config()
    dumped = config.model_dump(mode="json")
    entries: list[ConfigEntry] = []
    for field in iter_config_fields():
        section_dump = dumped.get(field.section)
        value = section_dump.get(field.key) if isinstance(section_dump, dict) else field.default
        source = config.sources.get(field.dotted, "default")
        entries.append(
            ConfigEntry(
                section=field.section,
                key=field.key,
                dotted=field.dotted,
                value=value,
                source=source,
                description=field.description,
                editable=source != "env" and not field.impact.immutable,
                widget=field.widget(),
                choices=field.choices,
                ge=field.ge,
                le=field.le,
                warning=field.impact.message(field.dotted),
                env_name=field.env_name,
            )
        )
    return entries


def history(limit: int = 50) -> list[SettingsChange]:
    return SettingsStore().history(limit)


def set_value(section: str, key: str, value: Any, *, source: Source, persist: bool = False) -> SetResult:
    """Valida e grava. `persist` grava mesmo quando o valor é o padrão."""
    field = require_field(section, key)
    batch = set_many([(section, key, value)], source=source, persist=persist)
    warning = batch.warnings[0] if batch.warnings else None
    return SetResult(field.dotted, changed=field.dotted in batch.changed, warning=warning)


def set_many(updates: list[tuple[str, str, Any]], *, source: Source, persist: bool = False) -> BatchResult:
    """Valida o conjunto e grava numa transação. Se falhar, nada entra no histórico."""
    prepared: dict[tuple[str, str], tuple[ConfigField, Any]] = {}
    for section, key, value in updates:
        field = require_field(section, key)
        _reject_locked(field)
        prepared[(section, key)] = (field, coerce(field, value))

    store = SettingsStore()
    current = store.load_overrides()
    candidate = {name: dict(values) for name, values in current.items()}
    pending: list[tuple[ConfigField, Any]] = []
    for field, coerced in prepared.values():
        table = current.get(field.section, {})
        in_db = field.key in table
        if in_db and table[field.key] == coerced:
            continue
        if not in_db and coerced == field.default and not persist:
            continue
        candidate.setdefault(field.section, {})[field.key] = coerced
        pending.append((field, coerced))
    if not pending:
        return BatchResult((), ())

    _validate_overrides(candidate)
    store.write_many([(field.section, field.key, value) for field, value in pending], source=source)
    clear_config_cache()
    changed: list[str] = []
    warnings: list[str] = []
    for field, _value in pending:
        changed.append(field.dotted)
        message = field.impact.message(field.dotted)
        if message and message not in warnings:
            warnings.append(message)
    return BatchResult(tuple(changed), tuple(warnings))


def unset_value(section: str, key: str, *, source: Source) -> SetResult:
    field = require_field(section, key)
    _reject_locked(field)
    store = SettingsStore()
    current = store.load_overrides()
    table = current.get(section, {})
    if key not in table:
        raise ConfigError(f"{field.dotted} já usa o padrão. Nada a remover.")
    candidate = {name: dict(values) for name, values in current.items()}
    candidate[section].pop(key, None)
    if not candidate[section]:
        candidate.pop(section)
    _validate_overrides(candidate)
    store.unset(section, key, source=source)
    clear_config_cache()
    return SetResult(field.dotted, changed=True, warning=field.impact.message(field.dotted))


def revert_change(change_id: int, *, source: Source) -> SetResult:
    change = SettingsStore().get_change(change_id)
    if change is None:
        raise ConfigError(f"Alteração {change_id} não está no histórico. Rode `nix config history`.")
    if change.section == VAULTS_SECTION:
        raise ConfigError(
            "Mudanças de vault não se desfazem com `nix config undo`. "
            "Use `nix vault` para renomear, remover, trocar a pasta, gravar um ajuste ou escolher o padrão."
        )
    if change.old_value is None:
        result = unset_value(change.section, change.key, source=source)
    else:
        result = set_value(change.section, change.key, change.old_value, source=source, persist=True)
    if not result.changed:
        raise ConfigError(f"{change.dotted} já está com o valor anterior. Nada mudou.")
    return result


def coerce(field: ConfigField, value: Any) -> Any:
    kind = field.widget()
    try:
        if kind == "bool":
            return _as_bool(field, value)
        if kind == "int":
            return _as_int(field, value)
        if kind == "float":
            return _as_float(field, value)
        if kind == "lines":
            return _as_lines(field, value)
        if kind == "json":
            return _as_object(field, value)
        if kind == "choice":
            return _as_choice(field, value)
        return _as_text(value)
    except ConfigError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigError(
            f"Valor inválido para {field.dotted}: {exc}. Confira o formato e rode `nix config list`."
        ) from exc


def _reject_locked(field: ConfigField) -> None:
    if field.impact.immutable:
        raise ConfigError(f"{field.dotted} não pode ser alterado. {field.description}")
    if env_defines(field.section, field.key):
        raise ConfigError(
            f"{field.dotted} está definido por {field.env_name} e essa variável ganha do settings.db. "
            f"Remova {field.env_name} para gravar o valor aqui."
        )


def _validate_overrides(overrides: dict[str, dict[str, Any]]) -> NixConfig:
    _db, env, merged = config_document(SettingsStore())
    candidate = deep_merge(overrides, env)
    candidate.pop("vault", None)
    candidate["vaults"] = merged["vaults"]
    try:
        return NixConfig.model_validate(candidate, context={"path_anchor": app_root()})
    except ValidationError as exc:
        parts = [f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise ConfigError(
            f"Configuração inválida ({'; '.join(parts)}). O valor não foi gravado."
        ) from exc
    except ConfigError as exc:
        raise ConfigError(f"{exc.message} O valor não foi gravado.") from exc


def _as_bool(field: ConfigField, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on", "sim"}:
            return True
        if lowered in {"false", "0", "no", "off", "nao", "não"}:
            return False
    raise ConfigError(f"{field.dotted} é sim ou não. Use true ou false.")


def _as_int(field: ConfigField, value: Any) -> int:
    if isinstance(value, bool | float):
        raise ConfigError(f"{field.dotted} precisa ser um inteiro.")
    if isinstance(value, int):
        return value
    return int(str(value).strip())


def _as_float(field: ConfigField, value: Any) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{field.dotted} precisa ser um número.")
    if isinstance(value, int | float):
        return float(value)
    return float(str(value).strip())


def _as_lines(field: ConfigField, value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ConfigError(f"{field.dotted} precisa ser uma lista JSON.")
        return [str(item) for item in parsed]
    return [line.strip() for line in text.splitlines() if line.strip()]


def _as_object(field: ConfigField, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ConfigError(f"{field.dotted} precisa ser um objeto JSON.")
    return parsed


def _as_choice(field: ConfigField, value: Any) -> str:
    text = str(value).strip()
    choices = field.choices or ()
    if text not in choices:
        allowed = ", ".join(choices)
        raise ConfigError(f"{field.dotted}={text!r} não é suportado. Use um de: {allowed}.")
    return text


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)
