"""Projeto da captura: raiz Git (ou a pasta) e o `.nix.toml` opcional."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from nix.core.brain.events import find_project


@dataclass(frozen=True)
class ProjectConfig:
    key: str
    name: str
    capture_enabled: bool
    exclude: tuple[str, ...]
    profile_contribute: bool
    profile_consume: bool


def resolve_project(cwd: str) -> ProjectConfig:
    """Lê o projeto do evento. Toml ilegível desliga a captura (falha fechada)."""
    key, folder_name = find_project(cwd)
    path = Path(key) / ".nix.toml"
    if not path.is_file():
        return ProjectConfig(key, folder_name, True, (), True, True)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return ProjectConfig(key, folder_name, False, (), True, True)
    if not isinstance(data, dict):
        return ProjectConfig(key, folder_name, False, (), True, True)
    name = _text(data.get("project")) or folder_name
    capture = data.get("capture")
    profile = data.get("profile")
    capture_map = capture if isinstance(capture, dict) else {}
    profile_map = profile if isinstance(profile, dict) else {}
    return ProjectConfig(
        key=key,
        name=name,
        capture_enabled=_bool(capture_map.get("enabled"), default=True),
        exclude=_strings(capture_map.get("exclude")),
        profile_contribute=_bool(profile_map.get("contribute"), default=True),
        profile_consume=_bool(profile_map.get("consume"), default=True),
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "nao", "não"}
    return default


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
