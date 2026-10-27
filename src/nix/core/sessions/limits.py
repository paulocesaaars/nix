"""Limites e padrões do sanitizador para o hook, sem carregar o Pydantic.

O hook lê a seção `sessions` direto do `settings.db` (somente leitura) e do
ambiente (`NIX_SESSIONS__CAMPO`). Valor ausente ou inválido cai no padrão: o
hook nunca falha por causa da configuração (RF-131).
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field

from nix.config.paths import settings_path
from nix.config.session_defaults import (
    DEFAULT_FOLDER,
    DEFAULT_MAX_PROMPT_BYTES,
    DEFAULT_MAX_TOOL_BYTES,
    clean_folder,
)
from nix.core.sessions.paths import readonly_uri


@dataclass(frozen=True)
class HookLimits:
    max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES
    max_tool_bytes: int = DEFAULT_MAX_TOOL_BYTES
    extra_redact_patterns: tuple[str, ...] = field(default_factory=tuple)
    folder: str = DEFAULT_FOLDER


def load_limits() -> HookLimits:
    raw = _from_db()
    raw.update(_from_env())
    return HookLimits(
        max_prompt_bytes=_positive_int(raw.get("max_prompt_bytes"), DEFAULT_MAX_PROMPT_BYTES),
        max_tool_bytes=_positive_int(raw.get("max_tool_bytes"), DEFAULT_MAX_TOOL_BYTES),
        extra_redact_patterns=_patterns(raw.get("extra_redact_patterns")),
        folder=_folder(raw.get("folder")),
    )


def _from_db() -> dict[str, object]:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        conn = sqlite3.connect(readonly_uri(path), uri=True, timeout=1.0)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute("SELECT key, value_json FROM settings WHERE section = 'sessions'").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    found: dict[str, object] = {}
    for key, value_json in rows:
        try:
            found[str(key)] = json.loads(value_json)
        except (TypeError, ValueError):
            continue
    return found


def _from_env() -> dict[str, object]:
    found: dict[str, object] = {}
    prefix = "NIX_SESSIONS__"
    for name, value in os.environ.items():
        if name.upper().startswith(prefix):
            found[name[len(prefix) :].lower()] = value
    return found


def _positive_int(value: object, default: int) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _folder(value: object) -> str:
    return clean_folder(str(value or "")) or DEFAULT_FOLDER


def _patterns(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item))
    return ()
