"""Configuração persistida em `{app_root}/settings.db`."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nix.config.paths import settings_path
from nix.config.schema import (
    DEFAULT_WIKI_NAME,
    WIKI_SETTING_KEYS,
    WikiSettings,
    default_wiki_settings,
)
from nix.core.errors import ConfigError, SchemaVersionError
from nix.core.models import utc_now_iso
from nix.observability.logging import get_logger

logger = get_logger("nix.config.store")

SCHEMA_VERSION = 3
_SCHEMA_V1 = 1
_SCHEMA_V2 = 2
WIKIS_SECTION = "wikis"
# Nome da tabela até o esquema 2. A migração só troca o cadastro; índice e backups ficam.
_LEGACY_WIKI_TABLE = "vaults"

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    section    TEXT NOT NULL,
    key        TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (section, key)
);

CREATE TABLE IF NOT EXISTS settings_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    section        TEXT NOT NULL,
    key            TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT,
    source         TEXT NOT NULL,
    changed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wikis (
    name          TEXT PRIMARY KEY COLLATE NOCASE,
    path          TEXT NOT NULL,
    is_default    INTEGER NOT NULL CHECK (is_default IN (0, 1)),
    settings_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS wikis_one_default
    ON wikis(is_default) WHERE is_default = 1;
"""


def schema_version_message(found: int) -> str:
    return (
        f"settings.db está na versão {found} e este Nix entende a versão {SCHEMA_VERSION}. "
        "Rode `nix init --force` para recriar a configuração. "
        "Isso apaga os ajustes gravados; as notas não são alteradas."
    )


@dataclass(frozen=True)
class WikiRecord:
    """Linha da tabela `wikis`. `settings` é o JSON dos ajustes daquela wiki."""

    name: str
    path: str
    is_default: bool
    settings: dict[str, Any]
    created_at: str
    updated_at: str

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "is_default": self.is_default,
            "settings": self.settings,
        }

    def payload(self) -> dict[str, Any]:
        """Campos para o `WikiSettings`. As colunas ganham do JSON."""
        body = dict(self.settings)
        body["name"] = self.name
        body["path"] = self.path
        body["is_default"] = self.is_default
        return body


@dataclass(frozen=True)
class SettingsChange:
    id: int
    section: str
    key: str
    old_value: Any
    new_value: Any
    source: str
    changed_at: str

    @property
    def dotted(self) -> str:
        return f"{self.section}.{self.key}"


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    return json.loads(raw)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._ensure_schema(conn)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_DDL)
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            return
        found = int(row["value"])
        if found == _SCHEMA_V1:
            _migrate_v1_to_v2(conn)
            found = _SCHEMA_V2
        if found == _SCHEMA_V2 or _table_exists(conn, _LEGACY_WIKI_TABLE):
            _migrate_v2_to_v3(conn)
            return
        if found == SCHEMA_VERSION:
            _migrate_v2_to_v3(conn)
            return
        raise SchemaVersionError(schema_version_message(found))

    def is_initialized(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()
                return row is not None and str(row["value"]) == "1"
        except SchemaVersionError:
            return False

    def schema_mismatch(self) -> SchemaVersionError | None:
        """Versão que este processo não abre. Não cria o arquivo nem altera o esquema.

        As versões 1 e 2 não são erro: o próximo acesso migra para a 3.
        """
        if not self.path.is_file():
            return None
        conn = sqlite3.connect(self.path, timeout=5.0)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise ConfigError(
                    f"Não foi possível ler {self.path}: {exc}. "
                    "Feche outros processos do Nix e tente de novo. "
                    "Se o arquivo estiver corrompido, rode `nix init --force`."
                ) from exc
            return SchemaVersionError(
                f"{self.path} não tem o esquema deste Nix. "
                "Rode `nix init --force` para recriar a configuração. "
                "Isso apaga os ajustes gravados; as notas não são alteradas."
            )
        except sqlite3.Error as exc:
            raise ConfigError(
                f"Não foi possível ler {self.path}: {exc}. "
                "Rode `nix init --force` para recriar a configuração. As notas não são alteradas."
            ) from exc
        finally:
            conn.close()
        if row is None:
            return None
        found = int(row[0])
        if found in {SCHEMA_VERSION, _SCHEMA_V1, _SCHEMA_V2}:
            return None
        return SchemaVersionError(schema_version_message(found))

    def recreate(self) -> None:
        """Apaga o settings.db para o próximo acesso criar o esquema atual."""
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix) if suffix else self.path
            if not candidate.exists():
                continue
            try:
                candidate.unlink()
            except OSError as exc:
                raise ConfigError(
                    f"Não foi possível apagar {candidate}: {exc}. "
                    "Feche o `nix ui` e os clientes MCP e rode `nix init --force` de novo."
                ) from exc

    def mark_initialized(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('initialized', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )

    def clear_all(self) -> None:
        """Apaga chaves, wikis, histórico e a marca de init. Mantém a versão do esquema."""
        with self._connect() as conn:
            conn.execute("DELETE FROM settings")
            conn.execute("DELETE FROM wikis")
            conn.execute("DELETE FROM settings_history")
            conn.execute("DELETE FROM meta WHERE key = 'initialized'")

    def load_overrides(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        found: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            rows = conn.execute("SELECT section, key, value_json FROM settings")
            for row in rows:
                found.setdefault(str(row["section"]), {})[str(row["key"])] = _decode(str(row["value_json"]))
        return found

    def updated_at(self) -> str | None:
        """Carimbo do reload a quente: muda a cada escrita, inclusive remoções.

        `MAX(updated_at)` sozinho não percebe um DELETE de linha que não era a
        mais recente. O id do histórico cresce a cada escrita e cobre esse caso.
        """
        if not self.path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT MAX(stamp) FROM (
                        SELECT MAX(updated_at) AS stamp FROM settings
                        UNION ALL
                        SELECT MAX(updated_at) AS stamp FROM wikis
                    )) AS stamp,
                    (SELECT MAX(id) FROM settings_history) AS change_id,
                    (SELECT COUNT(*) FROM wikis) AS wiki_count
                """
            ).fetchone()
            if row is None or (row["stamp"] is None and row["change_id"] is None):
                return None
            return f"{row['stamp']}|{row['change_id']}|{row['wiki_count']}"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Uma transação. O commit acontece ao sair sem erro."""
        with self._connect() as conn:
            yield conn

    def legacy_vault_names(self) -> list[str]:
        """O que ainda usa o nome antigo depois da migração idempotente."""
        if not self.path.is_file():
            return []
        found: list[str] = []
        with self._connect() as conn:
            if _table_exists(conn, _LEGACY_WIKI_TABLE):
                found.append("a tabela vaults")
            for section in ("vault", "vaults"):
                row = conn.execute(
                    "SELECT 1 FROM settings WHERE section = ? LIMIT 1",
                    (section,),
                ).fetchone()
                if row is not None:
                    found.append(f"a seção {section}")
                row = conn.execute(
                    "SELECT 1 FROM settings_history WHERE section = ? LIMIT 1",
                    (section,),
                ).fetchone()
                if row is not None:
                    found.append(f"o histórico {section}")
        return found

    def list_wikis(self) -> list[WikiRecord]:
        if not self.path.is_file():
            return []
        with self._connect() as conn:
            return wiki_rows(conn)

    def get_wiki(self, name: str) -> WikiRecord | None:
        if not self.path.is_file():
            return None
        with self._connect() as conn:
            return wiki_by_name(conn, name)

    def set_value(self, section: str, key: str, value: Any, *, source: str) -> bool:
        """Grava o valor. Devolve False se o JSON já era esse."""
        return bool(self.write_many([(section, key, value)], source=source))

    def unset(self, section: str, key: str, *, source: str) -> bool:
        return self._write(section, key, None, source=source)

    def write_many(
        self,
        updates: list[tuple[str, str, Any]],
        *,
        source: str,
        record_history: bool = True,
    ) -> list[tuple[str, str]]:
        """Grava vários campos numa transação. Devolve o que mudou.

        `record_history` falso grava o settings.db sem linha em `settings_history`.
        A marca `ui.editor_called` usa isso.
        """
        if not updates:
            return []
        changed: list[tuple[str, str]] = []
        with self._connect() as conn:
            now = utc_now_iso()
            for section, key, value in updates:
                if self._apply(
                    conn,
                    section,
                    key,
                    _encode(value),
                    source=source,
                    now=now,
                    record_history=record_history,
                ):
                    changed.append((section, key))
        return changed

    def _write(self, section: str, key: str, new_json: str | None, *, source: str) -> bool:
        with self._connect() as conn:
            return self._apply(conn, section, key, new_json, source=source, now=utc_now_iso())

    def _apply(
        self,
        conn: sqlite3.Connection,
        section: str,
        key: str,
        new_json: str | None,
        *,
        source: str,
        now: str,
        record_history: bool = True,
    ) -> bool:
        current = conn.execute(
            "SELECT value_json FROM settings WHERE section = ? AND key = ?",
            (section, key),
        ).fetchone()
        old_json = str(current["value_json"]) if current is not None else None
        if old_json == new_json:
            return False
        if new_json is None:
            conn.execute("DELETE FROM settings WHERE section = ? AND key = ?", (section, key))
        else:
            conn.execute(
                """
                INSERT INTO settings (section, key, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(section, key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (section, key, new_json, now),
            )
        if record_history:
            conn.execute(
                """
                INSERT INTO settings_history (section, key, old_value_json, new_value_json, source, changed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (section, key, old_json, new_json, source, now),
            )
        return True

    def history(
        self,
        limit: int = 50,
        *,
        skip: tuple[tuple[str, str], ...] = (),
    ) -> list[SettingsChange]:
        """Alterações recentes. `skip` tira campos que não são ajuste, como `ui.editor_called`."""
        if not self.path.is_file():
            return []
        where = ""
        params: list[Any] = []
        if skip:
            hidden = " OR ".join("(section = ? AND key = ?)" for _item in skip)
            where = f"WHERE NOT ({hidden})"
            for section, key in skip:
                params.extend((section, key))
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, section, key, old_value_json, new_value_json, source, changed_at
                FROM settings_history
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_change(row) for row in rows]

    def get_change(self, change_id: int) -> SettingsChange | None:
        if not self.path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, section, key, old_value_json, new_value_json, source, changed_at
                FROM settings_history
                WHERE id = ?
                """,
                (change_id,),
            ).fetchone()
        if row is None:
            return None
        return _change(row)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row is not None else 0


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Renomeia a tabela `vaults` para `wikis`. Não mexe no índice nem nos backups.

    O passo é idempotente: abrir um settings.db já na versão 3 não duplica dados
    nem regrava o arquivo quando não há nada antigo.
    """
    legacy_table = _table_exists(conn, _LEGACY_WIKI_TABLE)
    old_index = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'vaults_one_default'"
    ).fetchone()
    legacy_history = conn.execute(
        "SELECT 1 FROM settings_history WHERE section = 'vaults' LIMIT 1"
    ).fetchone()
    legacy_settings = conn.execute(
        "SELECT 1 FROM settings WHERE section = 'vault' LIMIT 1"
    ).fetchone()
    current = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    needs_version = current is None or str(current["value"]) != str(SCHEMA_VERSION)
    if not any((legacy_table, old_index, legacy_history, legacy_settings, needs_version)):
        return
    if legacy_table:
        wiki_count = _row_count(conn, "wikis") if _table_exists(conn, "wikis") else 0
        legacy_count = _row_count(conn, _LEGACY_WIKI_TABLE)
        if legacy_count and wiki_count:
            raise ConfigError(
                "O settings.db tem dados nas tabelas vaults e wikis ao mesmo tempo. "
                "Rode `nix init --force` para recriar a configuração. As notas não são alteradas. "
                "O índice e os backups não foram alterados."
            )
        if legacy_count and not wiki_count:
            conn.execute("DROP TABLE wikis")
            conn.execute(f"ALTER TABLE {_LEGACY_WIKI_TABLE} RENAME TO wikis")
        else:
            conn.execute(f"DROP TABLE {_LEGACY_WIKI_TABLE}")
    if old_index is not None:
        conn.execute("DROP INDEX IF EXISTS vaults_one_default")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS wikis_one_default ON wikis(is_default) WHERE is_default = 1"
    )
    if legacy_history is not None:
        conn.execute("UPDATE settings_history SET section = 'wikis' WHERE section = 'vaults'")
    if legacy_settings is not None:
        conn.execute("DELETE FROM settings WHERE section = 'vault'")
    if needs_version and current is not None:
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION),),
        )


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Copia a seção `vault` do esquema 1 para a tabela `wikis`.

    Sem `vault.path` não cria wiki. A wiki migrada guarda `legacy_layout` para
    continuar usando a raiz de `index.data_dir` e de `safety.backup_dir`.
    O número do esquema sobe no passo seguinte, para a versão 3.
    """
    raw, updated = _v1_wiki_values(conn)
    path = raw.get("path")
    path_text = path.strip().replace("\\", "/") if isinstance(path, str) else ""
    created = False
    if path_text:
        count = conn.execute("SELECT COUNT(*) AS n FROM wikis").fetchone()
        existing = int(count["n"]) if count is not None else 0
        if existing == 0:
            settings = _v1_wiki_settings(raw)
            record = WikiRecord(
                name=DEFAULT_WIKI_NAME,
                path=path_text,
                is_default=True,
                settings=settings,
                created_at=updated.get("path") or utc_now_iso(),
                updated_at=updated.get("path") or utc_now_iso(),
            )
            _require_migrated_wiki(record)
            now = record.updated_at
            insert_wiki_row(conn, record, source="migration", now=now)
            assert_one_default(conn)
            created = True
    conn.execute("DELETE FROM settings WHERE section = 'vault'")
    logger.info("settings.db: seção vault do esquema 1 copiada para a tabela wikis.")
    if created:
        logger.info(
            "A wiki %s foi para a tabela wikis. Índice e backups continuam na raiz.",
            DEFAULT_WIKI_NAME,
        )


def _v1_wiki_values(conn: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, str]]:
    rows = conn.execute(
        "SELECT key, value_json, updated_at FROM settings WHERE section = 'vault'"
    ).fetchall()
    found: dict[str, Any] = {}
    updated: dict[str, str] = {}
    for row in rows:
        key = str(row["key"])
        try:
            found[key] = json.loads(str(row["value_json"]))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "Não foi possível migrar o settings.db da versão 1: "
                f"o campo vault.{key} está ilegível. "
                "Rode `nix init --force` para recriar a configuração. "
                "As notas não são alteradas."
            ) from exc
        updated[key] = str(row["updated_at"])
    return found, updated


def _v1_wiki_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Copia só os ajustes que ainda validam. O resto fica no padrão do esquema 2."""
    settings = default_wiki_settings()
    for key in WIKI_SETTING_KEYS:
        if key not in raw:
            continue
        trial = dict(settings)
        trial[key] = raw[key]
        if _wiki_settings_ok(trial):
            settings[key] = raw[key]
    settings["legacy_layout"] = True
    return settings


def _wiki_settings_ok(settings: dict[str, Any]) -> bool:
    try:
        WikiSettings.model_validate(
            {
                "name": DEFAULT_WIKI_NAME,
                "path": "migrado",
                "is_default": True,
                **settings,
            }
        )
    except (ValidationError, ConfigError):
        return False
    return True


def _require_migrated_wiki(record: WikiRecord) -> None:
    try:
        WikiSettings.model_validate(record.payload())
    except (ValidationError, ConfigError) as exc:
        raise ConfigError(
            "Não foi possível migrar a wiki da versão 1 "
            f"({exc}). Rode `nix init --force` para recriar a configuração. "
            "As notas não são alteradas."
        ) from exc


def wiki_rows(conn: sqlite3.Connection) -> list[WikiRecord]:
    rows = conn.execute(
        """
        SELECT name, path, is_default, settings_json, created_at, updated_at
        FROM wikis
        ORDER BY is_default DESC, name COLLATE NOCASE
        """
    ).fetchall()
    return [_wiki_record(row) for row in rows]


def wiki_by_name(conn: sqlite3.Connection, name: str) -> WikiRecord | None:
    row = conn.execute(
        """
        SELECT name, path, is_default, settings_json, created_at, updated_at
        FROM wikis
        WHERE name = ?
        """,
        (name,),
    ).fetchone()
    if row is None:
        return None
    return _wiki_record(row)


def _wiki_record(row: sqlite3.Row) -> WikiRecord:
    raw_settings = str(row["settings_json"])
    try:
        parsed = json.loads(raw_settings)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "O cadastro de uma wiki está ilegível no settings.db. "
            "Rode `nix init --force` para recriar a configuração. As notas não são alteradas."
        ) from exc
    if not isinstance(parsed, dict):
        raise ConfigError(
            "O cadastro de uma wiki no settings.db não é um objeto. "
            "Rode `nix init --force` para recriar a configuração. As notas não são alteradas."
        )
    return WikiRecord(
        name=str(row["name"]),
        path=str(row["path"]),
        is_default=bool(int(row["is_default"])),
        settings=parsed,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def assert_one_default(conn: sqlite3.Connection) -> None:
    """Com wikis na tabela, exatamente um `is_default`. Lista vazia é o pré-init."""
    rows = conn.execute("SELECT is_default FROM wikis").fetchall()
    if not rows:
        return
    defaults = sum(1 for row in rows if int(row["is_default"]) == 1)
    if defaults != 1:
        raise ConfigError(
            "A configuração de wikis ficou sem exatamente um padrão. A operação foi cancelada. "
            "Use `nix wiki default NOME`."
        )


def insert_wiki_row(conn: sqlite3.Connection, record: WikiRecord, *, source: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO wikis (name, path, is_default, settings_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record.name,
            record.path,
            1 if record.is_default else 0,
            _encode(record.settings),
            record.created_at,
            record.updated_at,
        ),
    )
    _wiki_history(conn, record.name, None, record.snapshot(), source=source, now=now)


def rename_wiki_row(conn: sqlite3.Connection, old: str, new: str, *, source: str, now: str) -> None:
    current = wiki_by_name(conn, old)
    if current is None:
        raise ConfigError(f"Wiki {old!r} não existe. Veja os nomes com `nix wiki list`.")
    renamed = WikiRecord(
        name=new,
        path=current.path,
        is_default=current.is_default,
        settings=current.settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE wikis SET name = ?, updated_at = ? WHERE name = ?",
        (new, now, current.name),
    )
    _wiki_history(conn, current.name, current.snapshot(), renamed.snapshot(), source=source, now=now)


def update_wiki_settings_row(
    conn: sqlite3.Connection,
    name: str,
    settings: dict[str, Any],
    *,
    source: str,
    now: str,
) -> None:
    current = wiki_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Wiki {name!r} não existe. Veja os nomes com `nix wiki list`.")
    updated = WikiRecord(
        name=current.name,
        path=current.path,
        is_default=current.is_default,
        settings=settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE wikis SET settings_json = ?, updated_at = ? WHERE name = ?",
        (_encode(settings), now, current.name),
    )
    _wiki_history(conn, current.name, current.snapshot(), updated.snapshot(), source=source, now=now)


def update_wiki_path_row(conn: sqlite3.Connection, name: str, path: str, *, source: str, now: str) -> None:
    current = wiki_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Wiki {name!r} não existe. Veja os nomes com `nix wiki list`.")
    updated = WikiRecord(
        name=current.name,
        path=path,
        is_default=current.is_default,
        settings=current.settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE wikis SET path = ?, updated_at = ? WHERE name = ?",
        (path, now, current.name),
    )
    _wiki_history(conn, current.name, current.snapshot(), updated.snapshot(), source=source, now=now)


def delete_wiki_row(conn: sqlite3.Connection, name: str, *, source: str, now: str) -> None:
    current = wiki_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Wiki {name!r} não existe. Veja os nomes com `nix wiki list`.")
    conn.execute("DELETE FROM wikis WHERE name = ?", (current.name,))
    _wiki_history(conn, current.name, current.snapshot(), None, source=source, now=now)


def set_default_wiki_row(conn: sqlite3.Connection, name: str, *, source: str, now: str) -> None:
    """Marca um padrão. Zera os demais antes, para o índice único não rejeitar a troca."""
    current = wiki_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Wiki {name!r} não existe. Veja os nomes com `nix wiki list`.")
    previous = conn.execute("SELECT name FROM wikis WHERE is_default = 1").fetchone()
    previous_name = str(previous["name"]) if previous is not None else None
    if previous_name == current.name:
        return
    conn.execute("UPDATE wikis SET is_default = 0, updated_at = ?", (now,))
    conn.execute(
        "UPDATE wikis SET is_default = 1, updated_at = ? WHERE name = ?",
        (now, current.name),
    )
    _wiki_history(
        conn,
        "default",
        {"name": previous_name} if previous_name is not None else None,
        {"name": current.name},
        source=source,
        now=now,
    )


def _wiki_history(
    conn: sqlite3.Connection,
    key: str,
    old: Any,
    new: Any,
    *,
    source: str,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO settings_history (section, key, old_value_json, new_value_json, source, changed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            WIKIS_SECTION,
            key,
            None if old is None else _encode(old),
            None if new is None else _encode(new),
            source,
            now,
        ),
    )


def _change(row: sqlite3.Row) -> SettingsChange:
    old_raw = row["old_value_json"]
    new_raw = row["new_value_json"]
    return SettingsChange(
        id=int(row["id"]),
        section=str(row["section"]),
        key=str(row["key"]),
        old_value=_decode(str(old_raw) if old_raw is not None else None),
        new_value=_decode(str(new_raw) if new_raw is not None else None),
        source=str(row["source"]),
        changed_at=str(row["changed_at"]),
    )
