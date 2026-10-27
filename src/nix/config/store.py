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
    DEFAULT_VAULT_NAME,
    VAULT_SETTING_KEYS,
    VaultSettings,
    default_vault_settings,
)
from nix.core.errors import ConfigError, SchemaVersionError
from nix.core.models import utc_now_iso
from nix.observability.logging import get_logger

logger = get_logger("nix.config.store")

SCHEMA_VERSION = 2
_SCHEMA_V1 = 1
VAULTS_SECTION = "vaults"

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

CREATE TABLE IF NOT EXISTS vaults (
    name          TEXT PRIMARY KEY COLLATE NOCASE,
    path          TEXT NOT NULL,
    is_default    INTEGER NOT NULL CHECK (is_default IN (0, 1)),
    settings_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS vaults_one_default
    ON vaults(is_default) WHERE is_default = 1;
"""


def schema_version_message(found: int) -> str:
    return (
        f"settings.db está na versão {found} e este Nix entende a versão {SCHEMA_VERSION}. "
        "Rode `nix init --force` para recriar a configuração. "
        "Isso apaga os ajustes gravados; as notas do Obsidian não são alteradas."
    )


@dataclass(frozen=True)
class VaultRecord:
    """Linha da tabela `vaults`. `settings` é o JSON dos ajustes daquele vault."""

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
        """Campos para o `VaultSettings`. As colunas ganham do JSON."""
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
        if found == SCHEMA_VERSION:
            return
        if found == _SCHEMA_V1:
            _migrate_v1_to_v2(conn)
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

        A versão 1 não é erro: o próximo acesso migra para a 2.
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
                "Isso apaga os ajustes gravados; as notas do Obsidian não são alteradas."
            )
        except sqlite3.Error as exc:
            raise ConfigError(
                f"Não foi possível ler {self.path}: {exc}. "
                "Rode `nix init --force` para recriar a configuração. As notas do Obsidian não são alteradas."
            ) from exc
        finally:
            conn.close()
        if row is None:
            return None
        found = int(row[0])
        if found in {SCHEMA_VERSION, _SCHEMA_V1}:
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
        """Apaga chaves, vaults, histórico e a marca de init. Mantém a versão do esquema."""
        with self._connect() as conn:
            conn.execute("DELETE FROM settings")
            conn.execute("DELETE FROM vaults")
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
                        SELECT MAX(updated_at) AS stamp FROM vaults
                    )) AS stamp,
                    (SELECT MAX(id) FROM settings_history) AS change_id,
                    (SELECT COUNT(*) FROM vaults) AS vault_count
                """
            ).fetchone()
            if row is None or (row["stamp"] is None and row["change_id"] is None):
                return None
            return f"{row['stamp']}|{row['change_id']}|{row['vault_count']}"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Uma transação. O commit acontece ao sair sem erro."""
        with self._connect() as conn:
            yield conn

    def list_vaults(self) -> list[VaultRecord]:
        if not self.path.is_file():
            return []
        with self._connect() as conn:
            return vault_rows(conn)

    def get_vault(self, name: str) -> VaultRecord | None:
        if not self.path.is_file():
            return None
        with self._connect() as conn:
            return vault_by_name(conn, name)

    def set_value(self, section: str, key: str, value: Any, *, source: str) -> bool:
        """Grava o valor. Devolve False se o JSON já era esse."""
        return bool(self.write_many([(section, key, value)], source=source))

    def unset(self, section: str, key: str, *, source: str) -> bool:
        return self._write(section, key, None, source=source)

    def write_many(self, updates: list[tuple[str, str, Any]], *, source: str) -> list[tuple[str, str]]:
        """Grava vários campos e o histórico numa transação. Devolve o que mudou."""
        if not updates:
            return []
        changed: list[tuple[str, str]] = []
        with self._connect() as conn:
            now = utc_now_iso()
            for section, key, value in updates:
                if self._apply(conn, section, key, _encode(value), source=source, now=now):
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
        conn.execute(
            """
            INSERT INTO settings_history (section, key, old_value_json, new_value_json, source, changed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (section, key, old_json, new_json, source, now),
        )
        return True

    def history(self, limit: int = 50) -> list[SettingsChange]:
        if not self.path.is_file():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, section, key, old_value_json, new_value_json, source, changed_at
                FROM settings_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
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


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Copia `vault.path` para a tabela `vaults` e sobe o esquema para a versão 2.

    Sem `vault.path` não cria vault. O vault migrado guarda `legacy_layout` para
    continuar usando a raiz de `index.data_dir` e de `safety.backup_dir`.
    """
    raw, updated = _v1_vault_values(conn)
    path = raw.get("path")
    path_text = path.strip().replace("\\", "/") if isinstance(path, str) else ""
    created = False
    if path_text:
        count = conn.execute("SELECT COUNT(*) AS n FROM vaults").fetchone()
        existing = int(count["n"]) if count is not None else 0
        if existing == 0:
            settings = _v1_vault_settings(raw)
            record = VaultRecord(
                name=DEFAULT_VAULT_NAME,
                path=path_text,
                is_default=True,
                settings=settings,
                created_at=updated.get("path") or utc_now_iso(),
                updated_at=updated.get("path") or utc_now_iso(),
            )
            _require_migrated_vault(record)
            now = record.updated_at
            insert_vault_row(conn, record, source="migration", now=now)
            assert_one_default(conn)
            created = True
    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'schema_version'",
        (str(SCHEMA_VERSION),),
    )
    conn.execute("DELETE FROM settings WHERE section = 'vault'")
    logger.info("settings.db migrado da versão 1 para a %s.", SCHEMA_VERSION)
    if created:
        logger.info(
            "O vault %s foi para a tabela vaults. Índice e backups continuam na raiz.",
            DEFAULT_VAULT_NAME,
        )


def _v1_vault_values(conn: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, str]]:
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
                "As notas do Obsidian não são alteradas."
            ) from exc
        updated[key] = str(row["updated_at"])
    return found, updated


def _v1_vault_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Copia só os ajustes que ainda validam. O resto fica no padrão do esquema 2."""
    settings = default_vault_settings()
    for key in VAULT_SETTING_KEYS:
        if key not in raw:
            continue
        trial = dict(settings)
        trial[key] = raw[key]
        if _vault_settings_ok(trial):
            settings[key] = raw[key]
    settings["legacy_layout"] = True
    return settings


def _vault_settings_ok(settings: dict[str, Any]) -> bool:
    try:
        VaultSettings.model_validate(
            {
                "name": DEFAULT_VAULT_NAME,
                "path": "migrado",
                "is_default": True,
                **settings,
            }
        )
    except (ValidationError, ConfigError):
        return False
    return True


def _require_migrated_vault(record: VaultRecord) -> None:
    try:
        VaultSettings.model_validate(record.payload())
    except (ValidationError, ConfigError) as exc:
        raise ConfigError(
            "Não foi possível migrar o vault da versão 1 "
            f"({exc}). Rode `nix init --force` para recriar a configuração. "
            "As notas do Obsidian não são alteradas."
        ) from exc


def vault_rows(conn: sqlite3.Connection) -> list[VaultRecord]:
    rows = conn.execute(
        """
        SELECT name, path, is_default, settings_json, created_at, updated_at
        FROM vaults
        ORDER BY is_default DESC, name COLLATE NOCASE
        """
    ).fetchall()
    return [_vault_record(row) for row in rows]


def vault_by_name(conn: sqlite3.Connection, name: str) -> VaultRecord | None:
    row = conn.execute(
        """
        SELECT name, path, is_default, settings_json, created_at, updated_at
        FROM vaults
        WHERE name = ?
        """,
        (name,),
    ).fetchone()
    if row is None:
        return None
    return _vault_record(row)


def _vault_record(row: sqlite3.Row) -> VaultRecord:
    raw_settings = str(row["settings_json"])
    try:
        parsed = json.loads(raw_settings)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "O cadastro de um vault está ilegível no settings.db. "
            "Rode `nix init --force` para recriar a configuração. As notas do Obsidian não são alteradas."
        ) from exc
    if not isinstance(parsed, dict):
        raise ConfigError(
            "O cadastro de um vault no settings.db não é um objeto. "
            "Rode `nix init --force` para recriar a configuração. As notas do Obsidian não são alteradas."
        )
    return VaultRecord(
        name=str(row["name"]),
        path=str(row["path"]),
        is_default=bool(int(row["is_default"])),
        settings=parsed,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def assert_one_default(conn: sqlite3.Connection) -> None:
    """Com vaults na tabela, exatamente um `is_default`. Lista vazia é o pré-init."""
    rows = conn.execute("SELECT is_default FROM vaults").fetchall()
    if not rows:
        return
    defaults = sum(1 for row in rows if int(row["is_default"]) == 1)
    if defaults != 1:
        raise ConfigError(
            "A configuração de vaults ficou sem exatamente um padrão. A operação foi cancelada. "
            "Use `nix vault default NOME`."
        )


def insert_vault_row(conn: sqlite3.Connection, record: VaultRecord, *, source: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO vaults (name, path, is_default, settings_json, created_at, updated_at)
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
    _vault_history(conn, record.name, None, record.snapshot(), source=source, now=now)


def rename_vault_row(conn: sqlite3.Connection, old: str, new: str, *, source: str, now: str) -> None:
    current = vault_by_name(conn, old)
    if current is None:
        raise ConfigError(f"Vault {old!r} não existe. Veja os nomes com `nix vault list`.")
    renamed = VaultRecord(
        name=new,
        path=current.path,
        is_default=current.is_default,
        settings=current.settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE vaults SET name = ?, updated_at = ? WHERE name = ?",
        (new, now, current.name),
    )
    _vault_history(conn, current.name, current.snapshot(), renamed.snapshot(), source=source, now=now)


def update_vault_settings_row(
    conn: sqlite3.Connection,
    name: str,
    settings: dict[str, Any],
    *,
    source: str,
    now: str,
) -> None:
    current = vault_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Vault {name!r} não existe. Veja os nomes com `nix vault list`.")
    updated = VaultRecord(
        name=current.name,
        path=current.path,
        is_default=current.is_default,
        settings=settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE vaults SET settings_json = ?, updated_at = ? WHERE name = ?",
        (_encode(settings), now, current.name),
    )
    _vault_history(conn, current.name, current.snapshot(), updated.snapshot(), source=source, now=now)


def update_vault_path_row(conn: sqlite3.Connection, name: str, path: str, *, source: str, now: str) -> None:
    current = vault_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Vault {name!r} não existe. Veja os nomes com `nix vault list`.")
    updated = VaultRecord(
        name=current.name,
        path=path,
        is_default=current.is_default,
        settings=current.settings,
        created_at=current.created_at,
        updated_at=now,
    )
    conn.execute(
        "UPDATE vaults SET path = ?, updated_at = ? WHERE name = ?",
        (path, now, current.name),
    )
    _vault_history(conn, current.name, current.snapshot(), updated.snapshot(), source=source, now=now)


def delete_vault_row(conn: sqlite3.Connection, name: str, *, source: str, now: str) -> None:
    current = vault_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Vault {name!r} não existe. Veja os nomes com `nix vault list`.")
    conn.execute("DELETE FROM vaults WHERE name = ?", (current.name,))
    _vault_history(conn, current.name, current.snapshot(), None, source=source, now=now)


def set_default_vault_row(conn: sqlite3.Connection, name: str, *, source: str, now: str) -> None:
    """Marca um padrão. Zera os demais antes, para o índice único não rejeitar a troca."""
    current = vault_by_name(conn, name)
    if current is None:
        raise ConfigError(f"Vault {name!r} não existe. Veja os nomes com `nix vault list`.")
    previous = conn.execute("SELECT name FROM vaults WHERE is_default = 1").fetchone()
    previous_name = str(previous["name"]) if previous is not None else None
    if previous_name == current.name:
        return
    conn.execute("UPDATE vaults SET is_default = 0, updated_at = ?", (now,))
    conn.execute(
        "UPDATE vaults SET is_default = 1, updated_at = ? WHERE name = ?",
        (now, current.name),
    )
    _vault_history(
        conn,
        "default",
        {"name": previous_name} if previous_name is not None else None,
        {"name": current.name},
        source=source,
        now=now,
    )


def _vault_history(
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
            VAULTS_SECTION,
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
