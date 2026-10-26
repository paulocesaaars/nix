"""Configuração persistida em `{app_root}/settings.db`."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nix.config.paths import settings_path
from nix.core.errors import ConfigError
from nix.core.models import utc_now_iso

SCHEMA_VERSION = 1

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
"""


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
        if found != SCHEMA_VERSION:
            raise ConfigError(
                f"settings.db está na versão {found} e este Nix entende a versão {SCHEMA_VERSION}. "
                "Atualize o Nix para a versão que gravou esse arquivo."
            )

    def is_initialized(self) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()
            return row is not None and str(row["value"]) == "1"

    def mark_initialized(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('initialized', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )

    def clear_all(self) -> None:
        """Apaga chaves, histórico e a marca de init. Mantém a versão do esquema."""
        with self._connect() as conn:
            conn.execute("DELETE FROM settings")
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
        if not self.path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(updated_at) AS stamp FROM settings").fetchone()
            if row is None or row["stamp"] is None:
                return None
            return str(row["stamp"])

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
