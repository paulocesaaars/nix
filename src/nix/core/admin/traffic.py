"""Registro estruturado das chamadas MCP em `{app_root}/.nix/traffic.db`.

O servidor MCP grava; a interface local só lê, em modo somente leitura e sem
criar nada. Cada operação abre e fecha a conexão, porque os dois lados rodam
em processos diferentes. O esquema é criado uma vez por processo, na primeira
gravação.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from nix.config.paths import default_state_dir
from nix.core.models import utc_now_iso

_READY: set[Path] = set()
_KEEP = 5000
_PRUNE_EVERY = 200

_DDL = """
CREATE TABLE IF NOT EXISTS mcp_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at   TEXT NOT NULL,
    client      TEXT NOT NULL DEFAULT '',
    method      TEXT NOT NULL,
    tool        TEXT,
    arguments   TEXT,
    status      TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_tool ON mcp_calls(tool);
"""


@dataclass(frozen=True)
class TrafficCall:
    id: int
    called_at: str
    client: str
    method: str
    tool: str | None
    arguments: str | None
    status: str
    duration_ms: float
    error: str | None


@dataclass(frozen=True)
class TrafficSummary:
    calls: int
    failures: int
    avg_ms: float
    top_tool: str | None


@dataclass(frozen=True)
class TrafficSnapshot:
    calls: list[TrafficCall]
    summary: TrafficSummary
    tools: list[str]


def traffic_path() -> Path:
    return default_state_dir() / "traffic.db"


class TrafficStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or traffic_path()

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=2.0)
        try:
            if self.path not in _READY:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(_DDL)
                _READY.add(self.path)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection | None]:
        """Conexão somente leitura, ou `None` se ainda não há registro."""
        if not self.path.is_file():
            yield None
            return
        conn = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        client: str,
        method: str,
        tool: str | None,
        arguments: str | None,
        status: str,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        with self._writer() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mcp_calls (called_at, client, method, tool, arguments, status, duration_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), client, method, tool, arguments, status, round(duration_ms, 1), error),
            )
            last = cursor.lastrowid or 0
            if last % _PRUNE_EVERY == 0:
                conn.execute("DELETE FROM mcp_calls WHERE id <= ?", (last - _KEEP,))

    def snapshot(
        self,
        limit: int = 100,
        *,
        tool: str | None = None,
        status: str | None = None,
    ) -> TrafficSnapshot:
        """Chamadas recentes, resumo e ferramentas vistas, numa só conexão."""
        empty = TrafficSnapshot([], TrafficSummary(0, 0, 0.0, None), [])
        try:
            with self._reader() as conn:
                if conn is None:
                    return empty
                return TrafficSnapshot(
                    calls=self._recent(conn, limit, tool, status),
                    summary=self._summary(conn),
                    tools=self._tools(conn),
                )
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return empty
            raise

    def recent(self, limit: int = 100) -> list[TrafficCall]:
        return self.snapshot(limit).calls

    @staticmethod
    def _recent(
        conn: sqlite3.Connection, limit: int, tool: str | None, status: str | None
    ) -> list[TrafficCall]:
        clauses: list[str] = []
        params: list[object] = []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM mcp_calls {where} ORDER BY id DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [_call(row) for row in rows]

    @staticmethod
    def _summary(conn: sqlite3.Connection) -> TrafficSummary:
        totals = conn.execute(
            "SELECT COUNT(*) AS calls, "
            "COALESCE(SUM(status != 'ok'), 0) AS failures, "
            "COALESCE(AVG(duration_ms), 0) AS avg_ms "
            "FROM mcp_calls WHERE tool IS NOT NULL"
        ).fetchone()
        top = conn.execute(
            "SELECT tool FROM mcp_calls WHERE tool IS NOT NULL "
            "GROUP BY tool ORDER BY COUNT(*) DESC LIMIT 1"
        ).fetchone()
        return TrafficSummary(
            calls=int(totals["calls"]),
            failures=int(totals["failures"]),
            avg_ms=float(totals["avg_ms"]),
            top_tool=str(top["tool"]) if top else None,
        )

    @staticmethod
    def _tools(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT DISTINCT tool FROM mcp_calls WHERE tool IS NOT NULL ORDER BY tool"
        ).fetchall()
        return [str(row["tool"]) for row in rows]


def _call(row: sqlite3.Row) -> TrafficCall:
    return TrafficCall(
        id=int(row["id"]),
        called_at=str(row["called_at"]),
        client=str(row["client"] or ""),
        method=str(row["method"]),
        tool=row["tool"],
        arguments=row["arguments"],
        status=str(row["status"]),
        duration_ms=float(row["duration_ms"]),
        error=row["error"],
    )
