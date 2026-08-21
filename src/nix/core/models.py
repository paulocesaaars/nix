"""Tipos de domínio compartilhados entre as camadas do núcleo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any, Literal

FileStatus = Literal["indexed", "error", "ignored"]
SyncTrigger = Literal["manual", "writeback"]
WriteMode = Literal["replace", "patch"]
LinkDirection = Literal["outgoing", "incoming", "both"]


@dataclass(frozen=True)
class WikiLink:
    target: str
    heading: str | None = None
    alias: str | None = None

    def display(self) -> str:
        base = self.target
        if self.heading:
            base = f"{base}#{self.heading}"
        if self.alias:
            return f"{base}|{self.alias}"
        return base


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start_line: int
    end_line: int
    path: str


@dataclass
class ParsedNote:
    rel_path: str
    raw: str
    body: str
    frontmatter: dict[str, Any]
    title: str
    tags: list[str]
    links: list[WikiLink]
    headings: list[Heading]


@dataclass(frozen=True)
class FileMeta:
    rel_path: str
    mtime: float
    size_bytes: int
    is_symlink: bool = False


@dataclass(frozen=True)
class Chunk:
    id: str
    file_id: str
    ordinal: int
    heading_path: str
    content: str
    embed_text: str
    token_count: int
    start_line: int | None
    end_line: int | None
    title: str
    rel_path: str = ""
    tags: list[str] = field(default_factory=list)
    folder: str = ""
    mtime: float = 0.0


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    file_id: str
    rel_path: str
    title: str
    heading_path: str
    content: str
    score: float
    ordinal: int
    start_line: int | None
    end_line: int | None
    tags: list[str] = field(default_factory=list)
    folder: str = ""
    mtime: float = 0.0

    def citation(self) -> str:
        if self.heading_path:
            heading = self.heading_path.split(" > ")[-1]
            return f"[[{self.title}#{heading}]]"
        return f"[[{self.title}]]"


@dataclass(frozen=True)
class WriteResult:
    rel_path: str
    action: Literal["created", "updated", "appended", "deleted"]
    chunks_indexed: int
    indexed: bool
    backup_path: str | None = None
    message: str = ""


@dataclass
class SyncReport:
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    failed: int = 0
    chunks_created: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    trigger: SyncTrigger = "manual"

    def summary_pt(self) -> str:
        verb = "seriam processados" if self.dry_run else "processados"
        return (
            f"{self.added} adicionados, {self.updated} atualizados, "
            f"{self.removed} removidos, {self.skipped} inalterados, "
            f"{self.failed} com erro, {self.chunks_created} chunks {verb} "
            f"em {self.elapsed_seconds:.1f}s"
        )


@dataclass(frozen=True)
class IndexStatus:
    files: int
    chunks: int
    errors: int
    last_sync_at: str | None
    embedding_model: str | None
    vault_path: str | None
    stale: bool
    stale_reason: str | None = None
    data_dir: str = ""


@dataclass(frozen=True)
class NoteRef:
    rel_path: str
    title: str
    tags: list[str] = field(default_factory=list)
    mtime: float | None = None


@dataclass(frozen=True)
class NoteContent:
    rel_path: str
    title: str
    content: str
    frontmatter: dict[str, Any]
    tags: list[str]
    links: list[str]


@dataclass(frozen=True)
class SyncProgress:
    current: int
    total: int
    rel_path: str
    action: str


@dataclass(frozen=True)
class InsightDuplicate:
    title: str
    paths: list[str]


@dataclass(frozen=True)
class LinkSuggestion:
    rel_path: str
    title: str
    suggested_target: str
    reason: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def jsonable(value: Any) -> Any:
    """Converte valores YAML (date/datetime) em tipos serializáveis em JSON."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
