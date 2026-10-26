"""Formulário da configuração a partir do snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass

from nix.config.editor import ConfigEntry, coerce, require_field, set_many, snapshot
from nix.core.errors import ConfigError

_SECTIONS = {
    "vault": "Vault",
    "index": "Índice",
    "retrieval": "Busca",
    "safety": "Segurança",
    "logging": "Log",
}
_ORIGINS = {"env": "ambiente", "db": "settings.db", "default": "padrão"}


@dataclass(frozen=True)
class FieldView:
    dotted: str
    description: str
    widget: str
    editable: bool
    origin: str
    lock_message: str | None
    value_text: str
    checked: bool
    choices: tuple[str, ...]
    min_value: str | None
    max_value: str | None
    step: str
    source: str
    impacts: tuple[str, ...]


@dataclass(frozen=True)
class SettingsGroup:
    key: str
    title: str
    fields: tuple[FieldView, ...]


@dataclass(frozen=True)
class SaveResult:
    warnings: tuple[str, ...]
    error: str | None
    changed: bool


def field_groups() -> list[SettingsGroup]:
    groups: list[SettingsGroup] = []
    bucket: list[FieldView] = []
    section = ""
    title = ""
    for entry in snapshot():
        if entry.section != section:
            if bucket:
                groups.append(SettingsGroup(section, title, tuple(bucket)))
            section = entry.section
            title = _SECTIONS.get(section, section)
            bucket = []
        bucket.append(_view(entry))
    if bucket:
        groups.append(SettingsGroup(section, title, tuple(bucket)))
    return groups


def apply_form(form: dict[str, str]) -> SaveResult:
    """Grava o que mudou numa transação. Se o conjunto for inválido, nada é persistido."""
    updates: list[tuple[str, str, object]] = []
    for entry in snapshot():
        if not entry.editable:
            continue
        if entry.widget == "bool":
            candidate: object = entry.dotted in form
        elif entry.dotted not in form:
            continue
        else:
            candidate = form[entry.dotted]
        if _same(entry, candidate):
            continue
        updates.append((entry.section, entry.key, candidate))
    if not updates:
        return SaveResult((), None, False)
    try:
        result = set_many(updates, source="ui")
    except ConfigError as exc:
        return SaveResult((), exc.message, False)
    return SaveResult(result.warnings, None, bool(result.changed))


def _view(entry: ConfigEntry) -> FieldView:
    text = _value_text(entry)
    options = tuple(entry.choices or ())
    if entry.widget == "choice" and text not in options:
        options = (text, *options)
    if not entry.editable and entry.source == "env":
        lock = f"Travado por {entry.env_name}. Essa variável ganha do settings.db."
    elif not entry.editable:
        lock = "Campo fixo."
    else:
        lock = None
    return FieldView(
        dotted=entry.dotted,
        description=entry.description,
        widget=entry.widget,
        editable=entry.editable,
        origin=_ORIGINS.get(entry.source, entry.source),
        lock_message=lock,
        value_text=text,
        checked=entry.widget == "bool" and entry.value is True,
        choices=options,
        min_value=_limit(entry.ge, entry.widget),
        max_value=_limit(entry.le, entry.widget),
        step="1" if entry.widget == "int" else "any",
        source=entry.source,
        impacts=_impacts(entry),
    )


def _impacts(entry: ConfigEntry) -> tuple[str, ...]:
    impact = require_field(entry.section, entry.key).impact
    labels: list[str] = []
    if impact.requires_full_sync:
        labels.append("exige sync --full")
    elif impact.requires_sync:
        labels.append("exige sync")
    if impact.requires_restart:
        labels.append("exige reinício")
    if impact.immutable:
        labels.append("fixo")
    return tuple(labels)


def _value_text(entry: ConfigEntry) -> str:
    value = entry.value
    if entry.widget == "lines" and isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if entry.widget == "json":
        return json.dumps(value, ensure_ascii=False, indent=2)
    if entry.widget == "int" and isinstance(value, int | float) and not isinstance(value, bool):
        return str(int(value))
    if entry.widget == "float" and isinstance(value, int | float) and not isinstance(value, bool):
        return json.dumps(float(value))
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _limit(value: float | None, widget: str) -> str | None:
    if value is None or widget not in {"int", "float"}:
        return None
    if widget == "int":
        return str(int(value))
    return json.dumps(value)


def _same(entry: ConfigEntry, candidate: object) -> bool:
    try:
        coerced = coerce(require_field(entry.section, entry.key), candidate)
    except ConfigError:
        return False
    current = entry.value
    if coerced == current:
        return True
    if (
        isinstance(coerced, int | float)
        and isinstance(current, int | float)
        and not isinstance(coerced, bool)
        and not isinstance(current, bool)
    ):
        return float(coerced) == float(current)
    return False
