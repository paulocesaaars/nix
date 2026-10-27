"""Registro das sessões em `{app_root}/.nix/sessions.db` (SQLite em WAL, fora do vault).

Cada operação abre e fecha a conexão, com transação curta: vários hooks gravam
ao mesmo tempo sem corromper o banco (RNF-S2). Só a biblioteca padrão é
importada, porque o hook usa este módulo (RNF-S1).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nix.config.paths import default_state_dir
from nix.core.sessions.events import SessionEvent
from nix.core.sessions.paths import readonly_uri

_READY: set[Path] = set()
# Teto da varredura do id curto, que não dá para consultar direto no SQL.
_SHORT_ID_SCAN = 2000

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    key           TEXT PRIMARY KEY,
    agent         TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    project       TEXT NOT NULL,
    project_name  TEXT NOT NULL,
    cwd           TEXT NOT NULL DEFAULT '',
    started       TEXT NOT NULL,
    updated       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'aberta',
    note_path     TEXT,
    note_vault    TEXT,
    rendered_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project, updated);

CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT NOT NULL UNIQUE,
    session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    type        TEXT NOT NULL,
    tool        TEXT NOT NULL DEFAULT '',
    target      TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL DEFAULT '',
    is_error    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_key, seq);

CREATE TABLE IF NOT EXISTS handoffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,
    session_key TEXT NOT NULL,
    state       TEXT NOT NULL,
    text        TEXT NOT NULL,
    note_path   TEXT,
    created_at  TEXT NOT NULL,
    consumed_at TEXT,
    consumed_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_handoffs_project ON handoffs(project, state);

CREATE TABLE IF NOT EXISTS hook_projects (
    project      TEXT NOT NULL,
    agent        TEXT NOT NULL,
    hook_file    TEXT NOT NULL DEFAULT '',
    installed_at TEXT NOT NULL,
    PRIMARY KEY (project, agent)
);
"""


@dataclass(frozen=True)
class SessionRow:
    key: str
    agent: str
    session_id: str
    project: str
    project_name: str
    cwd: str
    started: str
    updated: str
    status: str
    note_path: str | None
    note_vault: str | None
    rendered_at: str | None
    events: int = 0

    @property
    def short_id(self) -> str:
        cleaned = "".join(ch for ch in self.session_id if ch.isalnum())
        return (cleaned or "sessao")[:8].lower()

    @property
    def open(self) -> bool:
        return self.status == "aberta"


@dataclass(frozen=True)
class ProjectRow:
    project: str
    name: str
    sessions: int
    updated: str


@dataclass(frozen=True)
class EventRow:
    seq: int
    ts: str
    type: str
    tool: str
    target: str
    text: str
    is_error: bool


@dataclass(frozen=True)
class HandoffRow:
    id: int
    project: str
    session_key: str
    state: str
    text: str
    note_path: str | None
    created_at: str
    consumed_at: str | None
    consumed_by: str | None


def sessions_db_path() -> Path:
    return default_state_dir() / "sessions.db"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or sessions_db_path()

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
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
        conn = sqlite3.connect(readonly_uri(self.path), uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _select(self, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        """Linhas da consulta, ou lista vazia se o banco ou a tabela ainda não existem."""
        try:
            with self._reader() as conn:
                if conn is None:
                    return []
                return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return []
            raise

    # -- hooks por projeto (RN-S1, RF-134) ---------------------------------

    def register_project(self, project: str, agent: str, hook_file: str = "") -> None:
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO hook_projects (project, agent, hook_file, installed_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(project, agent) DO UPDATE SET hook_file = excluded.hook_file",
                (project, agent, hook_file, utc_now_iso()),
            )

    def unregister_project(self, project: str, agent: str) -> None:
        with self._writer() as conn:
            conn.execute("DELETE FROM hook_projects WHERE project = ? AND agent = ?", (project, agent))

    def has_hooks(self, project: str, agent: str) -> bool:
        try:
            rows = self._select("SELECT 1 FROM hook_projects WHERE project = ? AND agent = ?", (project, agent))
        except sqlite3.OperationalError:
            return False
        return bool(rows)

    def hook_agents(self, project: str) -> list[str]:
        try:
            rows = self._select("SELECT agent FROM hook_projects WHERE project = ? ORDER BY agent", (project,))
        except sqlite3.OperationalError:
            return []
        return [str(row["agent"]) for row in rows]

    # -- eventos -------------------------------------------------------------

    def record(self, event: SessionEvent) -> bool:
        """Grava o evento. Devolve False quando o id já existia (RF-82)."""
        key = event.session_key
        reopen = event.type != "session-end"
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO sessions (key, agent, session_id, project, project_name, cwd, started, updated, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'aberta') "
                "ON CONFLICT(key) DO NOTHING",
                (
                    key,
                    event.agent,
                    event.session_id,
                    event.project,
                    event.project_name,
                    event.cwd,
                    event.ts,
                    event.ts,
                ),
            )
            cursor = conn.execute(
                "INSERT OR IGNORE INTO events (id, session_key, ts, type, tool, target, text, is_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event.id, key, event.ts, event.type, event.tool, event.target, event.text, int(event.is_error)),
            )
            inserted = cursor.rowcount > 0
            if inserted:
                status = "aberta" if reopen else "encerrada"
                conn.execute(
                    "UPDATE sessions SET updated = MAX(updated, ?), status = ?, "
                    "cwd = CASE WHEN cwd = '' THEN ? ELSE cwd END WHERE key = ?",
                    (event.ts, status, event.cwd, key),
                )
            return inserted

    # -- leitura --------------------------------------------------------------

    def list_sessions(
        self,
        *,
        project: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 50,
        with_events: bool = True,
    ) -> list[SessionRow]:
        """`with_events=False` pula a contagem de eventos por sessão (o hook não precisa dela)."""
        clauses: list[str] = []
        params: list[object] = []
        if project:
            clauses.append("s.project = ?")
            params.append(project)
        if agent:
            clauses.append("s.agent = ?")
            params.append(agent)
        if status:
            clauses.append("s.status = ?")
            params.append(status)
        return self._session_rows(clauses, params, limit, with_events)

    def _session_rows(
        self, clauses: list[str], params: list[object], limit: int, with_events: bool
    ) -> list[SessionRow]:
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        count = "(SELECT COUNT(*) FROM events e WHERE e.session_key = s.key)" if with_events else "0"
        sql = (
            f"SELECT s.*, {count} AS events "  # noqa: S608
            f"FROM sessions s {where} ORDER BY s.updated DESC, s.key LIMIT ?"
        )
        return [_session(row) for row in self._select(sql, [*params, limit])]

    def find_session(self, ref: str, *, project: str | None = None) -> SessionRow | None:
        """Acha pela chave `agente:id`, pelo id da sessão, pelo id curto ou por um prefixo único."""
        wanted = ref.strip()
        if not wanted:
            return None
        scope = ["s.project = ?"] if project else []
        scope_params: list[object] = [project] if project else []

        exact = self._session_rows(
            [*scope, "(s.key = ? COLLATE NOCASE OR s.session_id = ? COLLATE NOCASE)"],
            [*scope_params, wanted, wanted],
            1,
            False,
        )
        if exact:
            return exact[0]

        like = _escape_like(wanted) + "%"
        prefixed = self._session_rows(
            [*scope, "(s.session_id LIKE ? ESCAPE '\\' OR s.key LIKE ? ESCAPE '\\')"],
            [*scope_params, like, like],
            2,
            False,
        )
        if len(prefixed) == 1:
            return prefixed[0]

        # O id curto só mantém letras e números do id: nem sempre é um prefixo literal.
        folded = wanted.casefold()
        for row in self.list_sessions(project=project, limit=_SHORT_ID_SCAN, with_events=False):
            if row.short_id == folded:
                return row
        return None

    def projects(self) -> list[ProjectRow]:
        """Projetos com sessão gravada, do mais recente para o mais antigo."""
        rows = self._select(
            "SELECT project, MAX(project_name) AS name, COUNT(*) AS sessions, MAX(updated) AS updated "
            "FROM sessions GROUP BY project ORDER BY MAX(updated) DESC"
        )
        return [ProjectRow(str(r["project"]), str(r["name"]), int(r["sessions"]), str(r["updated"])) for r in rows]

    def latest_session(self, project: str) -> SessionRow | None:
        rows = self.list_sessions(project=project, limit=1)
        return rows[0] if rows else None

    def events_for(self, session_key: str, *, limit: int | None = None) -> list[EventRow]:
        sql = "SELECT * FROM events WHERE session_key = ? ORDER BY seq"
        params: list[object] = [session_key]
        if limit is not None:
            sql = (
                "SELECT * FROM (SELECT * FROM events WHERE session_key = ? ORDER BY seq DESC LIMIT ?) "
                "ORDER BY seq"
            )
            params.append(limit)
        return [_event(row) for row in self._select(sql, params)]

    def count_sessions(self, project: str | None = None, *, rendered_only: bool = False) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if rendered_only:
            clauses.append("note_path IS NOT NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._select(f"SELECT COUNT(*) AS n FROM sessions {where}", params)  # noqa: S608
        return int(rows[0]["n"]) if rows else 0

    def agent_counts(self, project: str) -> dict[str, int]:
        """Sessões por agente no projeto."""
        rows = self._select("SELECT agent, COUNT(*) AS n FROM sessions WHERE project = ? GROUP BY agent", (project,))
        return {str(row["agent"]): int(row["n"]) for row in rows}

    # -- handoff (RF-111 a RF-113) -----------------------------------------------

    def create_handoff(self, project: str, session_key: str, text: str, note_path: str | None) -> HandoffRow:
        """Cria o pendente do projeto. O pendente anterior vira `cancelado` (no máximo um por projeto)."""
        with self._writer() as conn:
            conn.execute(
                "UPDATE handoffs SET state = 'cancelado' WHERE project = ? AND state = 'pendente'", (project,)
            )
            cursor = conn.execute(
                "INSERT INTO handoffs (project, session_key, state, text, note_path, created_at) "
                "VALUES (?, ?, 'pendente', ?, ?, ?)",
                (project, session_key, text, note_path, utc_now_iso()),
            )
            row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _handoff(row)

    def pending_handoff(self, project: str) -> HandoffRow | None:
        rows = self._select(
            "SELECT * FROM handoffs WHERE project = ? AND state = 'pendente' ORDER BY id DESC LIMIT 1", (project,)
        )
        return _handoff(rows[0]) if rows else None

    def consume_handoff(self, project: str, consumer: str, *, not_from: str | None = None) -> HandoffRow | None:
        """Entrega o pendente uma única vez (RN-S3). Um UPDATE só: dois agentes não levam o mesmo.

        `not_from` evita que a sessão que gerou o handoff o receba de volta.
        """
        skip = "AND session_key != ?" if not_from else ""
        params: list[object] = [utc_now_iso(), consumer, project]
        if not_from:
            params.append(not_from)
        with self._writer() as conn:
            row = conn.execute(
                "UPDATE handoffs SET state = 'consumido', consumed_at = ?, consumed_by = ? "
                "WHERE id = (SELECT id FROM handoffs WHERE project = ? AND state = 'pendente' "  # noqa: S608
                f"{skip} ORDER BY id DESC LIMIT 1) AND state = 'pendente' RETURNING *",
                params,
            ).fetchone()
        return _handoff(row) if row else None

    def cancel_handoff(self, project: str) -> bool:
        with self._writer() as conn:
            cursor = conn.execute(
                "UPDATE handoffs SET state = 'cancelado' WHERE project = ? AND state = 'pendente'", (project,)
            )
            return cursor.rowcount > 0

    def list_handoffs(self, project: str, limit: int = 10) -> list[HandoffRow]:
        rows = self._select("SELECT * FROM handoffs WHERE project = ? ORDER BY id DESC LIMIT ?", (project, limit))
        return [_handoff(row) for row in rows]

    # -- nota no vault ------------------------------------------------------------

    def mark_rendered(self, session_key: str, note_path: str, vault: str) -> None:
        with self._writer() as conn:
            conn.execute(
                "UPDATE sessions SET note_path = ?, note_vault = ?, rendered_at = ? WHERE key = ?",
                (note_path, vault, utc_now_iso(), session_key),
            )

    # -- retenção (RF-86) ------------------------------------------------------------

    def purge(self, retention_days: int) -> int:
        """Apaga eventos de sessões encerradas há mais de `retention_days`. A nota fica no vault."""
        if retention_days <= 0 or not self.path.is_file():
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE session_key IN "
                "(SELECT key FROM sessions WHERE status = 'encerrada' AND updated < ?)",
                (cutoff,),
            )
            removed = cursor.rowcount
        if removed:
            conn = sqlite3.connect(self.path, timeout=5.0)
            try:
                conn.execute("VACUUM")
            finally:
                conn.close()
        return removed


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _session(row: sqlite3.Row) -> SessionRow:
    return SessionRow(
        key=str(row["key"]),
        agent=str(row["agent"]),
        session_id=str(row["session_id"]),
        project=str(row["project"]),
        project_name=str(row["project_name"]),
        cwd=str(row["cwd"] or ""),
        started=str(row["started"]),
        updated=str(row["updated"]),
        status=str(row["status"]),
        note_path=row["note_path"],
        note_vault=row["note_vault"],
        rendered_at=row["rendered_at"],
        events=int(row["events"]) if "events" in row.keys() else 0,  # noqa: SIM118
    )


def _handoff(row: sqlite3.Row) -> HandoffRow:
    return HandoffRow(
        id=int(row["id"]),
        project=str(row["project"]),
        session_key=str(row["session_key"]),
        state=str(row["state"]),
        text=str(row["text"]),
        note_path=row["note_path"],
        created_at=str(row["created_at"]),
        consumed_at=row["consumed_at"],
        consumed_by=row["consumed_by"],
    )


def _event(row: sqlite3.Row) -> EventRow:
    return EventRow(
        seq=int(row["seq"]),
        ts=str(row["ts"]),
        type=str(row["type"]),
        tool=str(row["tool"] or ""),
        target=str(row["target"] or ""),
        text=str(row["text"] or ""),
        is_error=bool(row["is_error"]),
    )
