"""Cadastro de wikis. Uma definição para a CLI e para a interface.

O editor genérico não grava `wiki.*`. Nome, caminho, padrão e o limite de
100 ficam aqui. `index.*`, `retrieval.*`, `safety.*` e `logging.*` continuam
globais.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, get_origin

from pydantic import ValidationError

from nix.config.loader import clear_config_cache, load_config
from nix.config.paths import app_root
from nix.config.schema import (
    DEFAULT_WIKI_NAME,
    MAX_WIKIS,
    WIKI_SETTING_KEYS,
    WikiSettings,
    default_wiki_settings,
    unknown_wiki_message,
    validate_wiki_name,
    wiki_paths_overlap,
)
from nix.config.store import (
    SettingsStore,
    WikiRecord,
    assert_one_default,
    delete_wiki_row,
    insert_wiki_row,
    rename_wiki_row,
    set_default_wiki_row,
    update_wiki_path_row,
    update_wiki_settings_row,
    wiki_by_name,
    wiki_rows,
)
from nix.core.errors import ConfigError
from nix.core.index.lock import sync_in_progress
from nix.core.models import utc_now_iso

__all__ = ["DEFAULT_WIKI_NAME", "WikiService"]


class WikiService:
    """Operações de wiki numa transação cada, com histórico em `section="wikis"`."""

    def __init__(self, store: SettingsStore | None = None) -> None:
        self._store = store or SettingsStore()

    def list_wikis(self) -> list[WikiSettings]:
        return [_to_settings(record) for record in self._store.list_wikis()]

    def add(self, name: str, path: str | Path, *, source: str = "wiki") -> WikiSettings:
        """Cadastra uma wiki. O primeiro vira o padrão."""
        clean_name = validate_wiki_name(name)
        clean_path = require_wiki_directory(path)
        now = utc_now_iso()
        created: WikiRecord | None = None
        try:
            with self._store.transaction() as conn:
                rows = wiki_rows(conn)
                if len(rows) >= MAX_WIKIS:
                    raise ConfigError(
                        f"O Nix aceita no máximo {MAX_WIKIS} wikis. "
                        "Remova um com `nix wiki remove NOME` antes de adicionar outro."
                    )
                existing = _match(rows, clean_name)
                if existing is not None:
                    raise ConfigError(
                        f"Já existe uma wiki chamado {existing.name!r}. "
                        "A comparação ignora maiúsculas. Escolha outro nome ou use `nix wiki rename`."
                    )
                _reject_overlap(clean_path, rows)
                created = WikiRecord(
                    name=clean_name,
                    path=clean_path,
                    is_default=not rows,
                    settings=default_wiki_settings(),
                    created_at=now,
                    updated_at=now,
                )
                insert_wiki_row(conn, created, source=source, now=now)
                assert_one_default(conn)
        except sqlite3.IntegrityError as exc:
            raise ConfigError(
                "Não foi possível gravar a wiki. Confira se o nome já existe "
                "(a comparação ignora maiúsculas) e rode `nix wiki list`."
            ) from exc
        clear_config_cache()
        if created is None:
            raise ConfigError("A wiki não foi gravado. Rode `nix wiki list` e tente de novo.")
        return _to_settings(created)

    def rename(self, old: str, new: str, *, source: str = "wiki") -> WikiSettings:
        """Troca o nome preservando a grafia nova. Não move índice nem backups."""
        new_name = validate_wiki_name(new)
        now = utc_now_iso()
        renamed: WikiRecord | None = None
        with self._store.transaction() as conn:
            rows = wiki_rows(conn)
            current = _match(rows, old)
            if current is None:
                raise ConfigError(unknown_wiki_message(old, _pairs(rows)))
            other = _match(rows, new_name)
            if other is not None and other.name.casefold() != current.name.casefold():
                raise ConfigError(
                    f"Já existe uma wiki chamado {other.name!r}. "
                    "A comparação ignora maiúsculas. Escolha outro nome."
                )
            if current.name != new_name:
                _refuse_if_syncing(current.name)
                rename_wiki_row(conn, current.name, new_name, source=source, now=now)
            renamed = wiki_by_name(conn, new_name)
            assert_one_default(conn)
        clear_config_cache()
        if renamed is None:
            raise ConfigError(
                f"A wiki {new_name!r} não ficou gravado. Rode `nix wiki list` e tente de novo."
            )
        return _to_settings(renamed)

    def remove(self, name: str, *, source: str = "wiki") -> None:
        """Remove uma wiki que não seja o último nem o padrão."""
        now = utc_now_iso()
        with self._store.transaction() as conn:
            rows = wiki_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_wiki_message(name, _pairs(rows)))
            if len(rows) <= 1:
                raise ConfigError(
                    f"A wiki {current.name!r} é a única. O Nix precisa de pelo menos uma wiki. "
                    "Adicione outro com `nix wiki add NOME CAMINHO` antes de remover este."
                )
            if current.is_default:
                raise ConfigError(
                    f"A wiki {current.name!r} é o padrão. "
                    "Defina outro com `nix wiki default NOME` antes de remover."
                )
            _refuse_brain_wiki(current.name)
            _refuse_if_syncing(current.name)
            delete_wiki_row(conn, current.name, source=source, now=now)
            assert_one_default(conn)
        clear_config_cache()

    def set_default(self, name: str, *, source: str = "wiki") -> WikiSettings:
        """Marca a wiki padrão. Os demais deixam de ser."""
        now = utc_now_iso()
        chosen: WikiRecord | None = None
        with self._store.transaction() as conn:
            rows = wiki_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_wiki_message(name, _pairs(rows)))
            set_default_wiki_row(conn, current.name, source=source, now=now)
            assert_one_default(conn)
            chosen = wiki_by_name(conn, current.name)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"A wiki {name!r} não ficou como padrão. Rode `nix wiki list` e tente de novo."
            )
        return _to_settings(chosen)

    def set_path(self, name: str, path: str | Path, *, source: str = "wiki") -> WikiSettings:
        """Troca a pasta de uma wiki já cadastrado. Usado pelo init na wiki padrão."""
        clean_path = require_wiki_directory(path)
        now = utc_now_iso()
        chosen: WikiRecord | None = None
        with self._store.transaction() as conn:
            rows = wiki_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_wiki_message(name, _pairs(rows)))
            if _same_path(current.path, clean_path):
                chosen = current
            else:
                _refuse_if_syncing(current.name)
                others = [row for row in rows if row.name.casefold() != current.name.casefold()]
                _reject_overlap(clean_path, others)
                update_wiki_path_row(conn, current.name, clean_path, source=source, now=now)
                chosen = wiki_by_name(conn, current.name)
            assert_one_default(conn)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"O caminho da wiki {name!r} não foi gravado. Rode `nix wiki list` e tente de novo."
            )
        return _to_settings(chosen)

    def set_setting(self, name: str, key: str, raw: str, *, source: str = "wiki") -> tuple[WikiSettings, str | None]:
        """Grava um ajuste da wiki. O segundo valor é o aviso de sincronização, se houver."""
        field = _setting_key(key)
        parsed = _parse_setting(field, raw)
        now = utc_now_iso()
        chosen: WikiRecord | None = None
        wrote = False
        with self._store.transaction() as conn:
            rows = wiki_rows(conn)
            current = _match(rows, name)
            if current is None:
                raise ConfigError(unknown_wiki_message(name, _pairs(rows)))
            _refuse_if_syncing(current.name)
            settings = dict(current.settings)
            settings[field] = parsed
            stored = _stored_settings(current, settings)
            if stored == current.settings:
                chosen = current
            else:
                wrote = True
                update_wiki_settings_row(conn, current.name, stored, source=source, now=now)
                chosen = wiki_by_name(conn, current.name)
            assert_one_default(conn)
        clear_config_cache()
        if chosen is None:
            raise ConfigError(
                f"O ajuste {field} da wiki {name!r} não foi gravado. Rode `nix wiki list` e tente de novo."
            )
        warning = None
        if wrote and field in {"include", "exclude", "follow_symlinks"}:
            warning = (
                f"A mudança em {field} da wiki {chosen.name} só entra no índice com "
                f"`nix sync --wiki {chosen.name}`."
            )
        return _to_settings(chosen), warning


def _setting_key(key: str) -> str:
    cleaned = key.strip()
    if cleaned == "legacy_layout":
        raise ConfigError(
            "legacy_layout é gravado na migração do settings.db e não se edita. "
            "O índice e os backups dessa wiki continuam na pasta de origem."
        )
    if cleaned == "path":
        raise ConfigError("A pasta da wiki muda com `nix wiki path NOME CAMINHO`.")
    if cleaned in {"name", "is_default"}:
        raise ConfigError(
            "O nome muda com `nix wiki rename ANTIGO NOVO` e o padrão com `nix wiki default NOME`."
        )
    if cleaned not in WIKI_SETTING_KEYS:
        joined = ", ".join(WIKI_SETTING_KEYS)
        raise ConfigError(
            f"Ajuste {key!r} não existe numa wiki. Use um de: {joined}. "
            'Exemplo: nix wiki set Default exclude \'[".trash/**"]\'.'
        )
    return cleaned


def _parse_setting(key: str, raw: str) -> Any:
    annotation = WikiSettings.model_fields[key].annotation
    origin = get_origin(annotation)
    if annotation is bool:
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "on", "sim"}:
            return True
        if lowered in {"false", "0", "no", "off", "nao", "não"}:
            return False
        raise ConfigError(
            f"{key} é sim ou não. Exemplo: `nix wiki set Default follow_symlinks false`."
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


def _stored_settings(current: WikiRecord, settings: dict[str, Any]) -> dict[str, Any]:
    payload = dict(settings)
    payload["name"] = current.name
    payload["path"] = current.path
    payload["is_default"] = current.is_default
    try:
        wiki = WikiSettings.model_validate(payload)
    except (ValidationError, ConfigError) as exc:
        detail: object = exc
        if isinstance(exc, ValidationError):
            detail = "; ".join(
                f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}" for err in exc.errors()
            )
        raise ConfigError(
            f"Ajuste inválido para a wiki {current.name} ({detail}). "
            f"Corrija o valor e rode `nix wiki set {current.name} CAMPO VALOR` de novo."
        ) from exc
    stored = {key: getattr(wiki, key) for key in WIKI_SETTING_KEYS}
    if wiki.legacy_layout:
        stored["legacy_layout"] = True
    return stored


def _refuse_brain_wiki(name: str) -> None:
    """A wiki das páginas não sai enquanto o Mega Brain estiver ligado."""
    try:
        config = load_config()
    except ConfigError:
        return
    if config.brain.enabled and config.brain.wiki.casefold() == name.casefold():
        raise ConfigError(
            f"A wiki {name!r} guarda as páginas do Mega Brain. "
            "Desligue com `nix config set brain.enabled false` antes de removê-la."
        )


def _refuse_if_syncing(name: str) -> None:
    if sync_in_progress(name):
        raise ConfigError(
            f"A sincronização da wiki {name} está em andamento. "
            "Espere ela terminar e tente de novo."
        )


def require_wiki_directory(path: str | Path) -> str:
    """Resolve a pasta e exige que ela já exista. Devolve o caminho com barras `/`."""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError as exc:
        raise ConfigError(
            f"Caminho de wiki inválido ({path}): {exc}. "
            "Informe a pasta da wiki, por exemplo C:/Notas/MinhaWiki."
        ) from exc
    shown = resolved.as_posix()
    if not resolved.exists():
        raise ConfigError(
            f"O diretório {shown} não existe. Crie a pasta e tente de novo "
            f'(por exemplo: mkdir "{shown}") ou rode `nix init --wiki {shown}`.'
        )
    if not resolved.is_dir():
        raise ConfigError(f"{shown} não é um diretório. Aponte para a pasta raiz da wiki.")
    return shown


def _match(rows: list[WikiRecord], name: str) -> WikiRecord | None:
    folded = name.strip().casefold()
    for row in rows:
        if row.name.casefold() == folded:
            return row
    return None


def _pairs(rows: list[WikiRecord]) -> list[tuple[str, bool]]:
    return [(row.name, row.is_default) for row in rows]


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def _reject_overlap(candidate: str, rows: list[WikiRecord]) -> None:
    left = Path(candidate)
    for row in rows:
        if wiki_paths_overlap(left, Path(row.path)):
            raise ConfigError(
                f"O caminho {candidate} coincide com a wiki {row.name!r} ({row.path}) "
                "ou um fica dentro do outro. "
                "Escolha uma pasta que não contenha nem esteja dentro de outra wiki."
            )


def _to_settings(record: WikiRecord) -> WikiSettings:
    try:
        wiki = WikiSettings.model_validate(record.payload())
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(
            f"A wiki {record.name!r} está com ajustes inválidos no settings.db ({detail}). "
            "Rode `nix init --force` para recriar a configuração. As notas não são alteradas."
        ) from exc
    wiki.path_anchor = app_root()
    return wiki
