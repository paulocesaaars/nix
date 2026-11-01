"""Registro do Mega Brain em `{app_root}/.nix/brain.db`.

Cada operação abre e fecha a conexão. O hook importa este módulo, então ele
fica só na biblioteca padrão. O `sessions.db` antigo não é lido nem migrado.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nix.config.paths import default_state_dir
from nix.core.brain.events import SessionEvent
from nix.core.brain.paths import readonly_uri
from nix.core.errors import ConfigError

_READY: set[Path] = set()
_WORD = re.compile(r"\w+", re.UNICODE)

_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    key        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    key          TEXT PRIMARY KEY,
    project_key  TEXT NOT NULL,
    project_name TEXT NOT NULL,
    agent        TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL,
    page_path    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_key, updated_at);

CREATE TABLE IF NOT EXISTS observations (
    id          TEXT PRIMARY KEY,
    session_key TEXT NOT NULL,
    project_key TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ts          TEXT NOT NULL,
    tool        TEXT NOT NULL DEFAULT '',
    target      TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL DEFAULT '',
    is_error    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_key, ts);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    observation_id UNINDEXED,
    project_key UNINDEXED,
    body
);

CREATE TABLE IF NOT EXISTS handoffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL,
    session_key TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL,
    offered_at  TEXT NOT NULL,
    consumed_at TEXT NOT NULL DEFAULT '',
    consumed_by TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS handoffs_one_open ON handoffs(project_key) WHERE status = 'offered';

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key  TEXT NOT NULL DEFAULT '',
    recipient    TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    delivered_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS token_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id   TEXT NOT NULL UNIQUE,
    session_key   TEXT NOT NULL DEFAULT '',
    project_key   TEXT NOT NULL,
    agent         TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL,
    sentence   TEXT NOT NULL,
    page_path  TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL,
    project_key TEXT NOT NULL,
    quote       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS page_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    page_path   TEXT NOT NULL,
    project_key TEXT NOT NULL DEFAULT '',
    useful      INTEGER NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hook_installs (
    scope        TEXT NOT NULL,
    project_key  TEXT NOT NULL DEFAULT '',
    agent        TEXT NOT NULL,
    hook_file    TEXT NOT NULL DEFAULT '',
    installed_at TEXT NOT NULL,
    PRIMARY KEY (scope, project_key, agent)
);
"""


def brain_db_path() -> Path:
    return default_state_dir() / "brain.db"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def fts_query(text: str) -> str:
    """Consulta FTS5 só com palavras, para o texto do usuário não virar operador."""
    words = _WORD.findall(text)
    if not words:
        return ""
    return " OR ".join(f'"{word}"' for word in words[:16])


@dataclass(frozen=True)
class ProjectRecord:
    key: str
    name: str


@dataclass(frozen=True)
class SessionRecord:
    key: str
    project_key: str
    project_name: str
    agent: str
    external_id: str
    started_at: str
    ended_at: str
    updated_at: str
    page_path: str
    status: str


@dataclass(frozen=True)
class HandoffRecord:
    id: int
    project_key: str
    session_key: str
    body: str
    status: str
    consumed_by: str


@dataclass(frozen=True)
class ProfileRecord:
    id: int
    category: str
    sentence: str
    page_path: str
    status: str


@dataclass(frozen=True)
class ObservationRecord:
    id: str
    session_key: str
    project_key: str
    kind: str
    ts: str
    tool: str
    target: str
    text: str
    is_error: bool


@dataclass(frozen=True)
class AgentTokenUsage:
    agent: str
    input_tokens: int
    output_tokens: int


class BrainStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or brain_db_path()

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            if self.path not in _READY:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(_DDL)
                _READY.add(self.path)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            with suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection | None]:
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
        try:
            with self._reader() as conn:
                if conn is None:
                    return []
                return list(conn.execute(sql, params).fetchall())
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return []
            raise

    def register_hook(self, *, scope: str, agent: str, project_key: str = "", hook_file: str = "") -> None:
        project = "" if scope == "global" else project_key
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO hook_installs (scope, project_key, agent, hook_file, installed_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, project_key, agent) DO UPDATE SET "
                "hook_file = excluded.hook_file, installed_at = excluded.installed_at",
                (scope, project, agent, hook_file, utc_now_iso()),
            )

    def unregister_hook(self, *, scope: str, agent: str, project_key: str = "") -> None:
        project = "" if scope == "global" else project_key
        with self._writer() as conn:
            conn.execute(
                "DELETE FROM hook_installs WHERE scope = ? AND project_key = ? AND agent = ?",
                (scope, project, agent),
            )

    def capture_allowed(self, project_key: str, agent: str) -> bool:
        rows = self._select(
            "SELECT 1 FROM hook_installs WHERE agent = ? AND "
            "(scope = 'global' OR (scope = 'project' AND project_key = ?)) LIMIT 1",
            (agent, project_key),
        )
        return bool(rows)

    def has_hooks(self, project_key: str, agent: str) -> bool:
        return self.capture_allowed(project_key, agent)

    def record(self, event: SessionEvent, project_name: str) -> None:
        """Grava o evento. Repetir o mesmo id não duplica a observação."""
        now = event.ts or utc_now_iso()
        key = event.storage_key
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO projects (key, name, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at",
                (event.project, project_name, now),
            )
            conn.execute(
                "INSERT INTO sessions (key, project_key, project_name, agent, external_id, started_at, "
                "updated_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'open') "
                "ON CONFLICT(key) DO UPDATE SET project_name = excluded.project_name, updated_at = excluded.updated_at",
                (key, event.project, project_name, event.agent, event.session_id, now, now),
            )
            inserted = conn.execute(
                "INSERT OR IGNORE INTO observations "
                "(id, session_key, project_key, kind, ts, tool, target, text, is_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    key,
                    event.project,
                    event.type,
                    now,
                    event.tool,
                    event.target,
                    event.text,
                    1 if event.is_error else 0,
                ),
            )
            if inserted.rowcount:
                body = " ".join(part for part in (event.text, event.target) if part).strip()
                if body:
                    conn.execute(
                        "INSERT INTO observations_fts (observation_id, project_key, body) VALUES (?, ?, ?)",
                        (event.id, event.project, body),
                    )
            if event.type == "session-end":
                conn.execute(
                    "UPDATE sessions SET status = 'ended', ended_at = ?, updated_at = ? WHERE key = ?",
                    (now, now, key),
                )

    def end_session(self, session_key: str, ts: str) -> None:
        with self._writer() as conn:
            conn.execute(
                "UPDATE sessions SET status = 'ended', ended_at = ?, updated_at = ? WHERE key = ?",
                (ts, ts, session_key),
            )

    def close_idle(self, hours: int, now: datetime | None = None) -> list[str]:
        """Encerra sessões abertas sem evento recente. `hours` 0 não encerra nada."""
        if hours <= 0:
            return []
        moment = now or datetime.now(UTC)
        cutoff = (moment - timedelta(hours=hours)).isoformat(timespec="seconds")
        stamp = moment.isoformat(timespec="seconds")
        with self._writer() as conn:
            rows = conn.execute(
                "SELECT key FROM sessions WHERE status = 'open' AND updated_at < ?",
                (cutoff,),
            ).fetchall()
            keys = [str(row["key"]) for row in rows]
            if keys:
                conn.executemany(
                    "UPDATE sessions SET status = 'ended', ended_at = ?, updated_at = ? WHERE key = ?",
                    [(stamp, stamp, key) for key in keys],
                )
        return keys

    def pending_pages(self) -> list[SessionRecord]:
        rows = self._select(
            "SELECT * FROM sessions WHERE status = 'ended' AND page_path = '' ORDER BY updated_at"
        )
        return [_session(row) for row in rows]

    def set_page_path(self, session_key: str, page_path: str) -> None:
        with self._writer() as conn:
            conn.execute("UPDATE sessions SET page_path = ? WHERE key = ?", (page_path, session_key))

    def observations(self, session_key: str) -> list[ObservationRecord]:
        rows = self._select(
            "SELECT * FROM observations WHERE session_key = ? ORDER BY ts, id",
            (session_key,),
        )
        return [_observation(row) for row in rows]

    def sessions_for(self, project_key: str) -> list[SessionRecord]:
        rows = self._select(
            "SELECT * FROM sessions WHERE project_key = ? ORDER BY updated_at DESC",
            (project_key,),
        )
        return [_session(row) for row in rows]

    def list_projects(self) -> list[ProjectRecord]:
        rows = self._select("SELECT key, name FROM projects ORDER BY name")
        return [ProjectRecord(str(row["key"]), str(row["name"])) for row in rows]

    def list_all_messages(self) -> list[tuple[int, str, str, str, str]]:
        rows = self._select(
            "SELECT id, project_key, recipient, body, status FROM messages ORDER BY id DESC"
        )
        return [
            (int(row["id"]), str(row["project_key"]), str(row["recipient"]), str(row["body"]), str(row["status"]))
            for row in rows
        ]

    def installed_agents(self, project_key: str) -> list[tuple[str, str]]:
        rows = self._select(
            "SELECT agent, scope FROM hook_installs WHERE scope = 'global' OR project_key = ? ORDER BY agent, scope",
            (project_key,),
        )
        return [(str(row["agent"]), str(row["scope"])) for row in rows]

    def token_usage_by_agent(self, project_key: str) -> list[AgentTokenUsage]:
        """Soma entrada e saída do projeto, uma linha por IA. Sem número, a IA não entra."""
        rows = self._select(
            "SELECT agent, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
            "FROM token_calls WHERE project_key = ? GROUP BY agent ORDER BY agent",
            (project_key,),
        )
        usage: list[AgentTokenUsage] = []
        for row in rows:
            incoming = row["input_tokens"]
            outgoing = row["output_tokens"]
            if incoming is None and outgoing is None:
                continue
            usage.append(
                AgentTokenUsage(
                    agent=str(row["agent"]),
                    input_tokens=int(incoming or 0),
                    output_tokens=int(outgoing or 0),
                )
            )
        return usage

    def recent_pages(self, project_key: str | None, limit: int) -> list[SessionRecord]:
        if project_key:
            rows = self._select(
                "SELECT * FROM sessions WHERE project_key = ? AND page_path != '' "
                "ORDER BY updated_at DESC LIMIT ?",
                (project_key, limit),
            )
        else:
            rows = self._select(
                "SELECT * FROM sessions WHERE page_path != '' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return [_session(row) for row in rows]

    def search_observations(self, query: str, project_key: str | None, limit: int = 8) -> list[dict[str, str]]:
        match = fts_query(query)
        if not match:
            return []
        sql = "SELECT observation_id, project_key, body FROM observations_fts WHERE observations_fts MATCH ?"
        params: list[object] = [match]
        if project_key:
            sql += " AND project_key = ?"
            params.append(project_key)
        sql += " LIMIT ?"
        params.append(limit)
        try:
            rows = self._select(sql, params)
        except sqlite3.OperationalError:
            return []
        return [
            {
                "observation_id": str(row["observation_id"]),
                "project_key": str(row["project_key"]),
                "text": str(row["body"]),
            }
            for row in rows
        ]

    def add_feedback(self, page_path: str, project_key: str, useful: bool, note: str) -> None:
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO page_feedback (page_path, project_key, useful, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (page_path, project_key, 1 if useful else 0, note, utc_now_iso()),
            )

    def create_handoff(self, project_key: str, session_key: str, body: str) -> int:
        """Abre um handoff. Recusa se o projeto já tem um em aberto."""
        try:
            with self._writer() as conn:
                existing = conn.execute(
                    "SELECT id FROM handoffs WHERE project_key = ? AND status = 'offered'",
                    (project_key,),
                ).fetchone()
                if existing is not None:
                    raise ConfigError(
                        "Já existe um handoff aberto neste projeto. "
                        "Aceite com `brain_handoff_accept` ou cancele com `brain_handoff_cancel`."
                    )
                cursor = conn.execute(
                    "INSERT INTO handoffs (project_key, session_key, body, status, offered_at) "
                    "VALUES (?, ?, ?, 'offered', ?)",
                    (project_key, session_key, body, utc_now_iso()),
                )
                return int(cursor.lastrowid or 0)
        except sqlite3.IntegrityError as exc:
            raise ConfigError(
                "Já existe um handoff aberto neste projeto. "
                "Aceite com `brain_handoff_accept` ou cancele com `brain_handoff_cancel`."
            ) from exc

    def offered_handoff(self, project_key: str) -> HandoffRecord | None:
        rows = self._select(
            "SELECT * FROM handoffs WHERE project_key = ? AND status = 'offered' ORDER BY id DESC LIMIT 1",
            (project_key,),
        )
        return _handoff(rows[0]) if rows else None

    def list_handoffs(self, project_key: str, limit: int = 10) -> list[HandoffRecord]:
        rows = self._select(
            "SELECT * FROM handoffs WHERE project_key = ? ORDER BY id DESC LIMIT ?",
            (project_key, limit),
        )
        return [_handoff(row) for row in rows]

    def accept_handoff(self, project_key: str, consumer: str) -> tuple[bool, str, str]:
        """Reivindica o handoff aberto. Devolve (ganhou, texto, quem ficou com ele)."""
        stamp = utc_now_iso()
        with self._writer() as conn:
            row = conn.execute(
                "SELECT id, body FROM handoffs WHERE project_key = ? AND status = 'offered' ORDER BY id LIMIT 1",
                (project_key,),
            ).fetchone()
            if row is None:
                claimed = conn.execute(
                    "SELECT consumed_by FROM handoffs WHERE project_key = ? AND status = 'consumed' "
                    "ORDER BY consumed_at DESC LIMIT 1",
                    (project_key,),
                ).fetchone()
                owner = str(claimed["consumed_by"]) if claimed is not None else ""
                return False, "", owner
            updated = conn.execute(
                "UPDATE handoffs SET status = 'consumed', consumed_at = ?, consumed_by = ? "
                "WHERE id = ? AND status = 'offered'",
                (stamp, consumer, int(row["id"])),
            )
            if updated.rowcount != 1:
                claimed = conn.execute(
                    "SELECT consumed_by FROM handoffs WHERE id = ?",
                    (int(row["id"]),),
                ).fetchone()
                owner = str(claimed["consumed_by"]) if claimed is not None and claimed["consumed_by"] else ""
                return False, "", owner
            return True, str(row["body"]), consumer

    def cancel_handoff(self, project_key: str) -> bool:
        with self._writer() as conn:
            updated = conn.execute(
                "UPDATE handoffs SET status = 'cancelled', consumed_at = ? "
                "WHERE project_key = ? AND status = 'offered'",
                (utc_now_iso(), project_key),
            )
            return updated.rowcount > 0

    def pending_messages(self, project_key: str, agent: str = "") -> int:
        sql = "SELECT COUNT(*) AS n FROM messages WHERE status = 'pending' AND (project_key = '' OR project_key = ?)"
        params: list[object] = [project_key]
        if agent:
            sql += " AND (recipient = '' OR lower(recipient) = ?)"
            params.append(agent.lower())
        rows = self._select(sql, params)
        if not rows:
            return 0
        return int(rows[0]["n"] or 0)

    def send_message(self, project_key: str, body: str, recipient: str = "") -> int:
        with self._writer() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (project_key, recipient, body, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (project_key, recipient.strip().lower(), body, utc_now_iso()),
            )
            return int(cursor.lastrowid or 0)

    def pop_message(self, project_key: str, agent: str = "") -> tuple[int, str] | None:
        """Entrega uma mensagem pendente. A segunda chamada concorrente não a vê."""
        with self._writer() as conn:
            sql = (
                "SELECT id, body FROM messages WHERE status = 'pending' "
                "AND (project_key = '' OR project_key = ?)"
            )
            params: list[object] = [project_key]
            if agent:
                sql += " AND (recipient = '' OR lower(recipient) = ?)"
                params.append(agent.lower())
            sql += " ORDER BY id LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            if row is None:
                return None
            updated = conn.execute(
                "UPDATE messages SET status = 'delivered', delivered_at = ? WHERE id = ? AND status = 'pending'",
                (utc_now_iso(), int(row["id"])),
            )
            if updated.rowcount != 1:
                return None
            return int(row["id"]), str(row["body"])

    def list_messages(self, project_key: str) -> list[tuple[int, str, str, str]]:
        rows = self._select(
            "SELECT id, recipient, body, status FROM messages "
            "WHERE project_key = '' OR project_key = ? ORDER BY id",
            (project_key,),
        )
        return [(int(row["id"]), str(row["recipient"]), str(row["body"]), str(row["status"])) for row in rows]

    def cancel_message(self, message_id: int) -> bool:
        with self._writer() as conn:
            updated = conn.execute(
                "UPDATE messages SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                (message_id,),
            )
            return updated.rowcount > 0

    def record_tokens(
        self,
        *,
        response_id: str,
        session_key: str,
        project_key: str,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> bool:
        """Grava o uso. O mesmo id de resposta não entra de novo."""
        with self._writer() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO token_calls "
                "(response_id, session_key, project_key, agent, model, input_tokens, output_tokens, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response_id,
                    session_key,
                    project_key,
                    agent,
                    model,
                    input_tokens,
                    output_tokens,
                    utc_now_iso(),
                ),
            )
            return cursor.rowcount > 0

    def profile_by_path(self, page_path: str) -> ProfileRecord | None:
        rows = self._select("SELECT * FROM profile_entries WHERE page_path = ? ORDER BY id DESC LIMIT 1", (page_path,))
        return _profile(rows[0]) if rows else None

    def upsert_profile(
        self,
        *,
        category: str,
        sentence: str,
        page_path: str,
        evidence: list[tuple[str, str]],
    ) -> int:
        """Cria ou atualiza a entrada ativa. Não mexe em lápide."""
        now = utc_now_iso()
        with self._writer() as conn:
            current = conn.execute(
                "SELECT id, status FROM profile_entries WHERE page_path = ? ORDER BY id DESC LIMIT 1",
                (page_path,),
            ).fetchone()
            if current is not None and str(current["status"]) == "tombstone":
                return int(current["id"])
            if current is None or str(current["status"]) != "active":
                cursor = conn.execute(
                    "INSERT INTO profile_entries (category, sentence, page_path, status, updated_at) "
                    "VALUES (?, ?, ?, 'active', ?)",
                    (category, sentence, page_path, now),
                )
                entry_id = int(cursor.lastrowid or 0)
            else:
                entry_id = int(current["id"])
                conn.execute(
                    "UPDATE profile_entries SET sentence = ?, updated_at = ? WHERE id = ?",
                    (sentence, now, entry_id),
                )
                conn.execute("DELETE FROM profile_evidence WHERE entry_id = ?", (entry_id,))
            conn.executemany(
                "INSERT INTO profile_evidence (entry_id, project_key, quote, created_at) VALUES (?, ?, ?, ?)",
                [(entry_id, project, quote, now) for project, quote in evidence],
            )
            return entry_id

    def tombstone_profile(self, page_path: str) -> bool:
        with self._writer() as conn:
            current = conn.execute(
                "SELECT id FROM profile_entries WHERE page_path = ? ORDER BY id DESC LIMIT 1",
                (page_path,),
            ).fetchone()
            if current is None:
                return False
            conn.execute(
                "UPDATE profile_entries SET status = 'tombstone', updated_at = ? WHERE id = ?",
                (utc_now_iso(), int(current["id"])),
            )
            return True

    def list_profile(self, status: str = "active") -> list[ProfileRecord]:
        rows = self._select(
            "SELECT * FROM profile_entries WHERE status = ? ORDER BY category, page_path",
            (status,),
        )
        return [_profile(row) for row in rows]

    def profile_evidence(self, entry_id: int) -> list[tuple[str, str]]:
        rows = self._select(
            "SELECT project_key, quote FROM profile_evidence WHERE entry_id = ? ORDER BY id",
            (entry_id,),
        )
        return [(str(row["project_key"]), str(row["quote"])) for row in rows]

    def token_lines(self, session_key: str) -> list[str]:
        rows = self._select(
            "SELECT agent, model, SUM(input_tokens) AS inp, SUM(output_tokens) AS outp "
            "FROM token_calls WHERE session_key = ? GROUP BY agent, model ORDER BY agent",
            (session_key,),
        )
        return [_token_line(row) for row in rows]


def _token_line(row: sqlite3.Row) -> str:
    agent = str(row["agent"]) or "desconhecido"
    model = str(row["model"]) or "desconhecido"
    return f"{agent} / {model}: {int(row['inp'] or 0)} entrada, {int(row['outp'] or 0)} saída"


def _session(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        key=str(row["key"]),
        project_key=str(row["project_key"]),
        project_name=str(row["project_name"]),
        agent=str(row["agent"]),
        external_id=str(row["external_id"]),
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"] or ""),
        updated_at=str(row["updated_at"]),
        page_path=str(row["page_path"] or ""),
        status=str(row["status"]),
    )


def _handoff(row: sqlite3.Row) -> HandoffRecord:
    return HandoffRecord(
        id=int(row["id"]),
        project_key=str(row["project_key"]),
        session_key=str(row["session_key"]),
        body=str(row["body"]),
        status=str(row["status"]),
        consumed_by=str(row["consumed_by"] or ""),
    )


def _profile(row: sqlite3.Row) -> ProfileRecord:
    return ProfileRecord(
        id=int(row["id"]),
        category=str(row["category"]),
        sentence=str(row["sentence"]),
        page_path=str(row["page_path"]),
        status=str(row["status"]),
    )


def _observation(row: sqlite3.Row) -> ObservationRecord:
    return ObservationRecord(
        id=str(row["id"]),
        session_key=str(row["session_key"]),
        project_key=str(row["project_key"]),
        kind=str(row["kind"]),
        ts=str(row["ts"]),
        tool=str(row["tool"] or ""),
        target=str(row["target"] or ""),
        text=str(row["text"] or ""),
        is_error=bool(row["is_error"]),
    )
