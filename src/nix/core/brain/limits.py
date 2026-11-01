"""Limites do hook e leitura leve da seção `brain`, sem Pydantic.

O hook não carrega o schema. Valor ausente ou inválido cai no padrão: o hook
nunca falha por causa da configuração.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from nix.config.paths import settings_path
from nix.core.brain.paths import readonly_uri

DEFAULT_MAX_PROMPT_BYTES = 16384
DEFAULT_MAX_TOOL_BYTES = 2048
DEFAULT_BRIEFING_MAX_BYTES = 3000
DEFAULT_IDLE_END_AFTER_HOURS = 0


@dataclass(frozen=True)
class HookLimits:
    max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES
    max_tool_bytes: int = DEFAULT_MAX_TOOL_BYTES
    extra_redact_patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BrainFlags:
    enabled: bool = False
    wiki: str = ""
    briefing_max_bytes: int = DEFAULT_BRIEFING_MAX_BYTES
    idle_end_after_hours: int = DEFAULT_IDLE_END_AFTER_HOURS


def load_limits() -> HookLimits:
    return HookLimits()


def load_brain_flags() -> BrainFlags:
    raw = _section("brain")
    return BrainFlags(
        enabled=_as_bool(raw.get("enabled")),
        wiki=_as_text(raw.get("wiki")),
        briefing_max_bytes=_as_int(raw.get("briefing_max_bytes"), DEFAULT_BRIEFING_MAX_BYTES),
        idle_end_after_hours=_as_int(raw.get("idle_end_after_hours"), DEFAULT_IDLE_END_AFTER_HOURS),
    )


def _section(name: str) -> dict[str, object]:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        conn = sqlite3.connect(readonly_uri(path), uri=True, timeout=1.0)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute("SELECT key, value_json FROM settings WHERE section = ?", (name,)).fetchall()
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


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim"}
    return False


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
