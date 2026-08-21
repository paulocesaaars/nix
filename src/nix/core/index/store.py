"""SQLite: estado do índice, chunks e FTS5."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from nix.core.errors import IndexCorruptError
from nix.core.models import jsonable, utc_now_iso

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS files (
    id            TEXT PRIMARY KEY,
    rel_path      TEXT NOT NULL UNIQUE,
    title         TEXT,
    content_hash  TEXT NOT NULL,
    mtime         REAL NOT NULL,
    size_bytes    INTEGER NOT NULL,
    frontmatter   TEXT,
    tags          TEXT,
    links         TEXT,
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    indexed_at    TEXT NOT NULL,
    status        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id            TEXT PRIMARY KEY,
    file_id       TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    ordinal       INTEGER NOT NULL,
    heading_path  TEXT,
    content       TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    token_count   INTEGER NOT NULL,
    start_line    INTEGER,
    end_line      INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, heading_path, title,
    content='chunks', content_rowid='rowid', tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    trigger      TEXT NOT NULL,
    added        INTEGER DEFAULT 0,
    updated      INTEGER DEFAULT 0,
    removed      INTEGER DEFAULT 0,
    failed       INTEGER DEFAULT 0,
    error_log    TEXT
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, content, heading_path, title)
  VALUES (new.rowid, new.content, new.heading_path, new.title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, heading_path, title)
  VALUES('delete', old.rowid, old.content, old.heading_path, old.title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, heading_path, title)
  VALUES('delete', old.rowid, old.content, old.heading_path, old.title);
  INSERT INTO chunks_fts(rowid, content, heading_path, title)
  VALUES (new.rowid, new.content, new.heading_path, new.title);
END;

CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
"""


class IndexStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_DDL)
        self._conn.commit()
        current = self.get_meta("schema_version")
        if current is None:
            self.set_meta("schema_version", SCHEMA_VERSION)
        elif current != SCHEMA_VERSION:
            raise IndexCorruptError(
                f"Schema do índice é {current}, esperado {SCHEMA_VERSION}. "
                "Apague o diretório de dados (index.data_dir) e rode `nix sync --full`."
            )

    def close(self) -> None:
        self._conn.close()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM index_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO index_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def list_files(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM files"))

    def get_file(self, rel_path: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute("SELECT * FROM files WHERE rel_path = ?", (rel_path,)).fetchone(),
        )

    def get_file_by_id(self, file_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone(),
        )

    def files_by_title(self, title: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM files WHERE lower(title) = lower(?) AND status = 'indexed'",
                (title,),
            )
        )

    def count_files(self, status: str | None = None) -> int:
        if status:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM files WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()
        return int(row["n"]) if row else 0

    def count_markdown(self, status: str = "indexed") -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE status = ? AND lower(rel_path) LIKE '%.md'",
            (status,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def indexed_bodies(self) -> list[tuple[str, str, str]]:
        """Título e corpo concatenado dos chunks, sem ler o vault."""
        parts: dict[str, list[str]] = {}
        titles: dict[str, str] = {}
        rows = self._conn.execute(
            """
            SELECT files.rel_path, files.title, chunks.content
            FROM files
            JOIN chunks ON chunks.file_id = files.id
            WHERE files.status = 'indexed' AND lower(files.rel_path) LIKE '%.md'
            ORDER BY files.rel_path, chunks.ordinal
            """
        )
        for row in rows:
            rel = str(row["rel_path"])
            titles[rel] = str(row["title"] or "")
            parts.setdefault(rel, []).append(str(row["content"] or ""))
        return [(rel, titles[rel], "\n".join(chunks)) for rel, chunks in parts.items()]

    def count_chunks(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"]) if row else 0

    def replace_file(
        self,
        *,
        file_id: str,
        rel_path: str,
        title: str,
        content_hash: str,
        mtime: float,
        size_bytes: int,
        frontmatter: dict[str, Any],
        tags: list[str],
        links: list[str],
        chunks: list[dict[str, Any]],
        status: str = "indexed",
    ) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            self._conn.execute(
                """
                INSERT INTO files (
                    id, rel_path, title, content_hash, mtime, size_bytes,
                    frontmatter, tags, links, chunk_count, indexed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    rel_path = excluded.rel_path,
                    title = excluded.title,
                    content_hash = excluded.content_hash,
                    mtime = excluded.mtime,
                    size_bytes = excluded.size_bytes,
                    frontmatter = excluded.frontmatter,
                    tags = excluded.tags,
                    links = excluded.links,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    status = excluded.status
                """,
                (
                    file_id,
                    rel_path,
                    title,
                    content_hash,
                    mtime,
                    size_bytes,
                    json.dumps(jsonable(frontmatter), ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(links, ensure_ascii=False),
                    len(chunks),
                    utc_now_iso(),
                    status,
                ),
            )
            self._conn.executemany(
                """
                INSERT INTO chunks (
                    id, file_id, ordinal, heading_path, content, title,
                    token_count, start_line, end_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c["id"],
                        file_id,
                        c["ordinal"],
                        c.get("heading_path") or "",
                        c["content"],
                        c.get("title") or title,
                        c["token_count"],
                        c.get("start_line"),
                        c.get("end_line"),
                    )
                    for c in chunks
                ],
            )

    def mark_error(self, file_id: str, rel_path: str, mtime: float, size_bytes: int) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO files (
                    id, rel_path, title, content_hash, mtime, size_bytes,
                    frontmatter, tags, links, chunk_count, indexed_at, status
                ) VALUES (?, ?, '', '', ?, ?, 'null', '[]', '[]', 0, ?, 'error')
                ON CONFLICT(id) DO UPDATE SET
                    status = 'error',
                    mtime = excluded.mtime,
                    size_bytes = excluded.size_bytes,
                    indexed_at = excluded.indexed_at
                """,
                (file_id, rel_path, mtime, size_bytes, utc_now_iso()),
            )

    def delete_file(self, file_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            self._conn.execute("DELETE FROM files WHERE id = ?", (file_id,))

    def update_stat(self, file_id: str, mtime: float, size_bytes: int) -> None:
        """Atualiza mtime/tamanho sem reindexar (hash igual, timestamp mudou)."""
        with self._conn:
            self._conn.execute(
                "UPDATE files SET mtime = ?, size_bytes = ? WHERE id = ?",
                (mtime, size_bytes, file_id),
            )

    def get_chunk(self, chunk_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute(
                "SELECT chunks.*, files.rel_path, files.tags AS file_tags, files.mtime "
                "FROM chunks JOIN files ON files.id = chunks.file_id WHERE chunks.id = ?",
                (chunk_id,),
            ).fetchone(),
        )

    def neighbor_chunks(self, file_id: str, ordinal: int, radius: int) -> list[sqlite3.Row]:
        if radius <= 0:
            return []
        return list(
            self._conn.execute(
                """
                SELECT chunks.*, files.rel_path, files.tags AS file_tags, files.mtime
                FROM chunks JOIN files ON files.id = chunks.file_id
                WHERE chunks.file_id = ? AND chunks.ordinal BETWEEN ? AND ?
                ORDER BY chunks.ordinal
                """,
                (file_id, ordinal - radius, ordinal + radius),
            )
        )

    def search_fts(self, query: str, limit: int) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                """
                SELECT chunks.id, chunks.file_id, chunks.ordinal, chunks.heading_path,
                       chunks.content, chunks.title, chunks.start_line, chunks.end_line,
                       files.rel_path, files.tags AS file_tags, files.mtime,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks ON chunks.rowid = chunks_fts.rowid
                JOIN files ON files.id = chunks.file_id
                WHERE chunks_fts MATCH ? AND files.status = 'indexed'
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
        )

    def list_notes(
        self,
        *,
        folder: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM files WHERE status = 'indexed'"
        params: list[Any] = []
        if folder:
            sql += " AND (rel_path LIKE ? OR rel_path LIKE ?)"
            folder = folder.strip("/").replace("\\", "/")
            params.extend([f"{folder}/%", folder])
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        sql += " ORDER BY title LIMIT ?"
        params.append(limit)
        return list(self._conn.execute(sql, params))

    def incoming_links(self, title: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM files WHERE status = 'indexed' AND links LIKE ?",
                (f"%{title}%",),
            )
        )

    def all_indexed_links(self) -> Iterator[tuple[str, str, list[str], list[str]]]:
        for row in self._conn.execute(
            "SELECT rel_path, title, links, tags FROM files WHERE status = 'indexed'"
        ):
            try:
                links = json.loads(row["links"] or "[]")
            except json.JSONDecodeError:
                links = []
            try:
                tags = [str(t) for t in json.loads(row["tags"] or "[]")]
            except json.JSONDecodeError:
                tags = []
            yield str(row["rel_path"]), str(row["title"] or ""), list(links), tags

    def insert_sync_run(
        self,
        *,
        trigger: str,
        added: int,
        updated: int,
        removed: int,
        failed: int,
        error_log: str,
        started_at: str,
        finished_at: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sync_runs (
                    started_at, finished_at, trigger, added, updated, removed, failed, error_log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, finished_at, trigger, added, updated, removed, failed, error_log),
            )

    def clear_all(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM chunks")
            self._conn.execute("DELETE FROM files")
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
