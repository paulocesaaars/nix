"""Cadastro de vaults. Uma definição para a CLI e para a interface.

O editor genérico não grava `vault.*`. Nome, caminho, padrão e o limite de
cinco ficam aqui. `index.*`, `retrieval.*`, `safety.*` e `logging.*` continuam
globais.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, get_origin

from pydantic import ValidationError

from nix.config.loader import clear_config_cache
from nix.config.paths import app_root
from nix.config.schema import (
    DEFAULT_VAULT_NAME,
    MAX_VAULTS,
    VAULT_SETTING_KEYS,
    VaultSettings,
    default_vault_settings,
    unknown_vault_message,
    validate_vault_name,
    vault_paths_overlap,
)
from nix.config.store import (
    SettingsStore,
    VaultRecord,
    assert_one_default,
    delete_vault_row,
    insert_vault_row,
    rename_vault_row,
    set_default_vault_row,
    update_vault_path_row,
    update_vault_settings_row,
    vault_by_name,
    vault_rows,
)
from nix.core.errors import ConfigError
from nix.core.index.lock import sync_in_progress
from nix.core.models import utc_now_iso

__all__ = ["DEFAULT_VAULT_NAME", "VaultService"]


class VaultService:
    """Operações de vault numa transação cada, com histórico em `section="vaults"`."""

    def __init__(self, store: SettingsStore | None = None) -> None:
        self._store = store or SettingsStore()

    def list_vaults(self) -> list[VaultSettings]:
        return [_to_settings(record) for record in self._store.list_vaults()]

    def add(self, name: str, path: str | Path, *, source: str = "vault") -> VaultSettings:
        """Cadastra um vault. O primeiro vira o padrão."""
        clean_name = validate_vault_name(name)
        clean_path = require_vault_directory(path)
        now = utc_now_iso()
        created: VaultRecord | None = None
        try:
            with self._store.transaction() as conn:
                rows = vault_rows(conn)
                if len(rows) >= MAX_VAULTS:
                    raise ConfigError(
                        f"O Nix aceita no máximo {MAX_VAULTS} vaults. "
                        "Remova um com `nix vault remove NOME` antes de adicionar outro."
                    )
                existing = _match(rows, clean_name)
                if existing is not None:
                    raise ConfigError(
                        f"Já existe um vault chamado {existing.name!r}. "
                        "A comparação ignora maiúsculas. Escolha outro nome ou use `nix vault rename`."
                    )
                _reject_overlap(clean_path, rows)
                created = VaultRecord(
                    name=clean_name,
                    path=clean_path,
                    is_default=not rows,
                    settings=default_vault_settings(),
                    created_at=now,
                    updated_at=now,
                )
                insert_vault_row(conn, created, source=source, now=now)
                assert_one_default(conn)
        except sqlite3.IntegrityError as exc:
            raise ConfigError(
                "Não foi possível gravar o vault. Confira se o nome já existe "
                "(a comparação ignora maiúsculas) e rode `nix vault list`."
            ) from exc
        clear_config_cache()
        if created is None:
            raise ConfigError("O vault não foi gravado. Rode `nix vault list` e tente de novo.")
        return _to_settings(created)

    def rename(self, old: str, new: str, *, source: str = "vault") -> VaultSettings:
        """Troca o nome preservando a grafia nova. Não move índice nem backups."""
        new_name = validate_vault_name(new)
        now = utc_now_iso()
        renamed: VaultRecord | None = None
        with self._store.transaction() as conn:
            rows = vault_rows(conn)
            current = _match(rows, old)
            if current is None:
                raise ConfigError(unknown_vault_message(old, _pairs(rows)))
            other = _match(rows, new_name)
            if other is not None and other.name.casefold() != current.name.casefold():
                raise ConfigError(
                    f"Já existe um vault chamado {other.name!r}. "
                    "A comparação ignora maiúsculas. Escolha outro nome."
                )
            if current.name != new_name:
                _refuse_if_syncing(current.name)
                rename_vault_row(conn, current.name, new_name, source=source, now=now)
            renamed = vault_by_name(conn, new_name)
            assert_one_default(conn)
        clear_config_cache()
        if renamed is None:
            raise ConfigError(
                f"O vault {new_name!r} não ficou gravado. Rode `nix vault list` e tente de novo."
            )
        return _to_settings(renamed)

    def remove(self, name: str, *, source: str = "vault") -> None:
        """Remove um vault que não seja o último nem o padrão."""
        now = utc_now_iso()
        with self._store.transaction() as conn:
            rows = vault_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_vault_message(name, _pairs(rows)))
            if len(rows) <= 1:
                raise ConfigError(
                    f"O vault {current.name!r} é o único. O Nix precisa de pelo menos um vault. "
                    "Adicione outro com `nix vault add NOME CAMINHO` antes de remover este."
                )
            if current.is_default:
                raise ConfigError(
                    f"O vault {current.name!r} é o padrão. "
                    "Defina outro com `nix vault default NOME` antes de remover."
                )
            _refuse_if_syncing(current.name)
            delete_vault_row(conn, current.name, source=source, now=now)
            assert_one_default(conn)
        clear_config_cache()

    def set_default(self, name: str, *, source: str = "vault") -> VaultSettings:
        """Marca o vault padrão. Os demais deixam de ser."""
        now = utc_now_iso()
        chosen: VaultRecord | None = None
        with self._store.transaction() as conn:
            rows = vault_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_vault_message(name, _pairs(rows)))
            set_default_vault_row(conn, current.name, source=source, now=now)
            assert_one_default(conn)
            chosen = vault_by_name(conn, current.name)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"O vault {name!r} não ficou como padrão. Rode `nix vault list` e tente de novo."
            )
        return _to_settings(chosen)

    def set_path(self, name: str, path: str | Path, *, source: str = "vault") -> VaultSettings:
        """Troca a pasta de um vault já cadastrado. Usado pelo init no vault padrão."""
        clean_path = require_vault_directory(path)
        now = utc_now_iso()
        chosen: VaultRecord | None = None
        with self._store.transaction() as conn:
            rows = vault_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_vault_message(name, _pairs(rows)))
            if _same_path(current.path, clean_path):
                chosen = current
            else:
                _refuse_if_syncing(current.name)
                others = [row for row in rows if row.name.casefold() != current.name.casefold()]
                _reject_overlap(clean_path, others)
                update_vault_path_row(conn, current.name, clean_path, source=source, now=now)
                chosen = vault_by_name(conn, current.name)
            assert_one_default(conn)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"O caminho do vault {name!r} não foi gravado. Rode `nix vault list` e tente de novo."
            )
        return _to_settings(chosen)

    def set_setting(self, name: str, key: str, raw: str, *, source: str = "vault") -> tuple[VaultSettings, str | None]:
        """Grava um ajuste do vault. O segundo valor é o aviso de sincronização, se houver."""
        field = _setting_key(key)
        parsed = _parse_setting(field, raw)
        now = utc_now_iso()
        chosen: VaultRecord | None = None
        wrote = False
        with self._store.transaction() as conn:
            rows = vault_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_vault_message(name, _pairs(rows)))
            _refuse_if_syncing(current.name)
            settings = dict(current.settings)
            settings[field] = parsed
            stored = _stored_settings(current, settings)
            if stored == current.settings:
                chosen = current
            else:
                wrote = True
                update_vault_settings_row(conn, current.name, stored, source=source, now=now)
                chosen = vault_by_name(conn, current.name)
            assert_one_default(conn)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"O ajuste {field} do vault {name!r} não foi gravado. Rode `nix vault list` e tente de novo."
            )
        warning = None
        if wrote and field in {"include", "exclude", "follow_symlinks"}:
            warning = (
                f"A mudança em {field} do vault {chosen.name} só entra no índice com "
                f"`nix sync --vault {chosen.name}`."
            )
        return _to_settings(chosen), warning


def _setting_key(key: str) -> str:
    cleaned = key.strip()
    if cleaned == "legacy_layout":
        raise ConfigError(
            "legacy_layout é gravado na migração do settings.db e não se edita. "
            "O índice e os backups desse vault continuam na pasta de origem."
        )
    if cleaned == "path":
        raise ConfigError("A pasta do vault muda com `nix vault path NOME CAMINHO`.")
    if cleaned in {"name", "is_default"}:
        raise ConfigError(
            "O nome muda com `nix vault rename ANTIGO NOVO` e o padrão com `nix vault default NOME`."
        )
    if cleaned not in VAULT_SETTING_KEYS:
        joined = ", ".join(VAULT_SETTING_KEYS)
        raise ConfigError(
            f"Ajuste {key!r} não existe num vault. Use um de: {joined}. "
            'Exemplo: nix vault set Default exclude \'[".trash/**"]\'.'
        )
    return cleaned


def _parse_setting(key: str, raw: str) -> Any:
    annotation = VaultSettings.model_fields[key].annotation
    origin = get_origin(annotation)
    if annotation is bool:
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "on", "sim"}:
            return True
        if lowered in {"false", "0", "no", "off", "nao", "não"}:
            return False
        raise ConfigError(
            f"{key} é sim ou não. Exemplo: `nix vault set Default follow_symlinks false`."
        )
    if origin in {list, dict}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            example = '[".trash/**"]' if origin is list else '{"created": "auto"}'
            raise ConfigError(
                f"O valor de {key} precisa ser JSON ({exc}). Exemplo: {example}."
            ) from exc
    return raw


def _stored_settings(current: VaultRecord, settings: dict[str, Any]) -> dict[str, Any]:
    payload = dict(settings)
    payload["name"] = current.name
    payload["path"] = current.path
    payload["is_default"] = current.is_default
    try:
        vault = VaultSettings.model_validate(payload)
    except (ValidationError, ConfigError) as exc:
        detail: object = exc
        if isinstance(exc, ValidationError):
            detail = "; ".join(
                f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}" for err in exc.errors()
            )
        raise ConfigError(
            f"Ajuste inválido para o vault {current.name} ({detail}). "
            f"Corrija o valor e rode `nix vault set {current.name} CAMPO VALOR` de novo."
        ) from exc
    stored = {key: getattr(vault, key) for key in VAULT_SETTING_KEYS}
    if vault.legacy_layout:
        stored["legacy_layout"] = True
    return stored


def _refuse_if_syncing(name: str) -> None:
    if sync_in_progress(name):
        raise ConfigError(
            f"A sincronização do vault {name} está em andamento. "
            "Espere ela terminar e tente de novo."
        )


def require_vault_directory(path: str | Path) -> str:
    """Resolve a pasta e exige que ela já exista. Devolve o caminho com barras `/`."""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError as exc:
        raise ConfigError(
            f"Caminho de vault inválido ({path}): {exc}. "
            "Informe a pasta do Obsidian, por exemplo C:/Obsidian/MeuVault."
        ) from exc
    shown = resolved.as_posix()
    if not resolved.exists():
        raise ConfigError(
            f"O diretório {shown} não existe. Crie a pasta e tente de novo "
            f'(por exemplo: mkdir "{shown}") ou rode `nix init --vault {shown}`.'
        )
    if not resolved.is_dir():
        raise ConfigError(f"{shown} não é um diretório. Aponte para a pasta raiz do vault do Obsidian.")
    return shown


def _match(rows: list[VaultRecord], name: str) -> VaultRecord | None:
    folded = name.strip().casefold()
    for row in rows:
        if row.name.casefold() == folded:
            return row
    return None


def _pairs(rows: list[VaultRecord]) -> list[tuple[str, bool]]:
    return [(row.name, row.is_default) for row in rows]


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def _reject_overlap(candidate: str, rows: list[VaultRecord]) -> None:
    left = Path(candidate)
    for row in rows:
        if vault_paths_overlap(left, Path(row.path)):
            raise ConfigError(
                f"O caminho {candidate} coincide com o vault {row.name!r} ({row.path}) "
                "ou um fica dentro do outro. "
                "Escolha uma pasta que não contenha nem esteja dentro de outro vault."
            )


def _to_settings(record: VaultRecord) -> VaultSettings:
    try:
        vault = VaultSettings.model_validate(record.payload())
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(
            f"O vault {record.name!r} está com ajustes inválidos no settings.db ({detail}). "
            "Rode `nix init --force` para recriar a configuração. As notas do Obsidian não são alteradas."
        ) from exc
    vault.path_anchor = app_root()
    return vault
