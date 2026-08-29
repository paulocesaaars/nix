"""Sincronização incremental do índice (RN-01: só quando o usuário pede)."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from nix.config.schema import NixConfig
from nix.core.errors import IndexIncompatibleError, PathEscapeError, VaultError
from nix.core.index.attachments import is_pdf_path, parse_pdf, referenced_pdfs
from nix.core.index.chunker import Chunker
from nix.core.index.embedder import Embedder
from nix.core.index.store import IndexStore
from nix.core.index.vectorstore import VectorStore
from nix.core.models import Chunk, FileMeta, ParsedNote, SyncProgress, SyncReport, utc_now_iso
from nix.core.vault.markdown import parse_markdown
from nix.core.vault.paths import assert_accessible
from nix.core.vault.reader import VaultReader
from nix.observability.logging import get_logger

logger = get_logger("nix.index.sync")

FILE_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
ProgressCb = Callable[[SyncProgress], None]


def file_id_for(rel_path: str) -> str:
    return str(uuid.uuid5(FILE_NS, rel_path.replace("\\", "/")))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Indexer:
    def __init__(
        self,
        config: NixConfig,
        store: IndexStore,
        vectors: VectorStore,
        embedder: Embedder,
        reader: VaultReader | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.vectors = vectors
        self.embedder = embedder
        self.reader = reader or VaultReader(config)
        self.chunker = Chunker(config.index)
        self._on_change = on_change

    def notify_change(self) -> None:
        if self._on_change:
            self._on_change()

    def _check_model(self, *, full: bool) -> None:
        stored = self.store.get_meta("embedding_model")
        current = self.config.index.embedding_model
        if stored and stored != current and not full:
            raise IndexIncompatibleError(
                f"O índice foi criado com {stored}, mas a configuração pede {current}. "
                "Rode `nix sync --full` para reconstruir o índice (vetores de espaços diferentes "
                "não podem ser misturados)."
            )

    def sync(
        self,
        *,
        full: bool = False,
        dry_run: bool = False,
        progress: ProgressCb | None = None,
        trigger: str = "manual",
    ) -> SyncReport:
        started = utc_now_iso()
        t0 = time.perf_counter()
        self._check_model(full=full)
        report = SyncReport(dry_run=dry_run, trigger=trigger if trigger in ("manual", "writeback") else "manual")  # type: ignore[arg-type]

        known = {str(row["rel_path"]): row for row in self.store.list_files()}
        extras = ["**/*.pdf"] if self.config.index.index_attachments else None
        scanned = {m.rel_path: m for m in self.reader.iter_files(extra_globs=extras)}
        if not self.config.index.index_attachments:
            scanned = {k: v for k, v in scanned.items() if k.lower().endswith(".md")}

        to_remove = [path for path in known if path not in scanned]
        candidates: list[FileMeta] = []
        for rel, meta in scanned.items():
            row = known.get(rel)
            if full or row is None:
                candidates.append(meta)
                continue
            if float(row["mtime"]) != meta.mtime or int(row["size_bytes"]) != meta.size_bytes:
                candidates.append(meta)
            else:
                report.skipped += 1

        total = len(candidates) + len(to_remove)
        current = 0

        if dry_run:
            for meta in candidates:
                current += 1
                action = "add" if meta.rel_path not in known else "update"
                if action == "add":
                    report.added += 1
                else:
                    report.updated += 1
                if progress:
                    progress(SyncProgress(current, total, meta.rel_path, action))
            report.removed = len(to_remove)
            for rel in to_remove:
                current += 1
                if progress:
                    progress(SyncProgress(current, total, rel, "remove"))
            report.elapsed_seconds = time.perf_counter() - t0
            return report

        if full:
            self.vectors.reset()
            self.store.clear_all()
            known = {}
            to_remove = []

        if candidates:
            if progress:
                progress(
                    SyncProgress(0, total or 1, self.config.index.embedding_model, "load_model")
                )
            logger.info(
                "Preparando embedding %s para %d arquivo(s). "
                "Em CPU, cada nota pode levar minutos; o progresso só avança ao terminar o arquivo.",
                self.config.index.embedding_model,
                len(candidates),
            )
            self.embedder.ensure_loaded()

        for meta in candidates:
            current += 1
            action = "add" if meta.rel_path not in known else "update"
            if progress:
                progress(SyncProgress(current, total or 1, meta.rel_path, action))
            try:
                note, content_hash = self._load_note(meta)
                row = known.get(meta.rel_path)
                if (
                    row is not None
                    and str(row["content_hash"] or "") == content_hash
                    and str(row["status"]) == "indexed"
                ):
                    self.store.update_stat(
                        file_id_for(meta.rel_path), meta.mtime, meta.size_bytes
                    )
                    report.skipped += 1
                    continue
                n_chunks = self._commit_index(meta, note, content_hash)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao indexar %s", meta.rel_path)
                report.failed += 1
                report.errors.append(f"{meta.rel_path}: {exc}")
                self.store.mark_error(
                    file_id_for(meta.rel_path), meta.rel_path, meta.mtime, meta.size_bytes
                )
                continue
            report.chunks_created += n_chunks
            if action == "add":
                report.added += 1
            else:
                report.updated += 1

        for rel in to_remove:
            current += 1
            if progress:
                progress(SyncProgress(current, total or 1, rel, "remove"))
            fid = str(known[rel]["id"])
            self.vectors.delete_file(fid)
            self.store.delete_file(fid)
            report.removed += 1

        self.store.set_meta("embedding_model", self.config.index.embedding_model)
        self.store.set_meta("vault_path", str(self.config.vault.root))
        self.store.set_meta("last_sync_at", datetime.now(UTC).isoformat())
        if self.embedder.dim:
            self.store.set_meta("dim", str(self.embedder.dim))
        report.elapsed_seconds = time.perf_counter() - t0
        self.store.insert_sync_run(
            trigger=trigger,
            added=report.added,
            updated=report.updated,
            removed=report.removed,
            failed=report.failed,
            error_log="\n".join(report.errors),
            started_at=started,
            finished_at=utc_now_iso(),
        )
        self.notify_change()
        return report

    def index_file(self, meta: FileMeta) -> int:
        note, content_hash = self._load_note(meta)
        return self._commit_index(meta, note, content_hash)

    def _commit_index(self, meta: FileMeta, note: ParsedNote, content_hash: str) -> int:
        fid = file_id_for(meta.rel_path)
        chunks = self.chunker.chunk_note(note, fid, mtime=meta.mtime)
        logger.info("Vetorizando %s (%d chunk(s)) em CPU.", meta.rel_path, len(chunks))
        embeddings = self.embedder.embed([c.embed_text for c in chunks])
        self.vectors.delete_file(fid)
        self.vectors.upsert(chunks, embeddings)
        self.store.replace_file(
            file_id=fid,
            rel_path=meta.rel_path,
            title=note.title,
            content_hash=content_hash,
            mtime=meta.mtime,
            size_bytes=meta.size_bytes,
            frontmatter=note.frontmatter,
            tags=note.tags,
            links=[link.target for link in note.links],
            chunks=[_chunk_row(c) for c in chunks],
            status="indexed",
        )
        if self.config.index.index_attachments and meta.rel_path.lower().endswith(".md"):
            self._index_referenced_pdfs(note)
        return len(chunks)

    def _load_note(self, meta: FileMeta) -> tuple[ParsedNote, str]:
        if is_pdf_path(meta.rel_path):
            data = self.reader.read_bytes(meta.rel_path, apply_include=False)
            return parse_pdf(meta.rel_path, data), sha256_bytes(data)
        raw = self.reader.read_text(meta.rel_path)
        return parse_markdown(meta.rel_path, raw), sha256_text(raw)

    def _index_referenced_pdfs(self, note: ParsedNote) -> None:
        for rel in referenced_pdfs(note.body, note.rel_path):
            try:
                assert_accessible(
                    rel,
                    self.config.vault.include,
                    self.config.vault.exclude,
                    apply_include=False,
                )
            except PathEscapeError:
                continue
            if not self.reader.exists(rel, apply_include=False):
                continue
            path = self.reader.resolve(rel)
            stat = path.stat()
            pdf_meta = FileMeta(rel_path=rel, mtime=stat.st_mtime, size_bytes=stat.st_size)
            row = self.store.get_file(rel)
            if row and float(row["mtime"]) == pdf_meta.mtime and int(row["size_bytes"]) == pdf_meta.size_bytes:
                continue
            try:
                self.index_file(pdf_meta)
            except (VaultError, Exception) as exc:  # noqa: BLE001
                logger.warning("PDF referenciado não indexado (%s): %s", rel, exc)


def _chunk_row(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "ordinal": chunk.ordinal,
        "heading_path": chunk.heading_path,
        "content": chunk.content,
        "title": chunk.title,
        "token_count": chunk.token_count,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def json_safe(report: SyncReport) -> dict[str, Any]:
    return {
        "added": report.added,
        "updated": report.updated,
        "removed": report.removed,
        "skipped": report.skipped,
        "failed": report.failed,
        "chunks_created": report.chunks_created,
        "elapsed_seconds": report.elapsed_seconds,
        "errors": report.errors,
        "dry_run": report.dry_run,
        "summary": report.summary_pt(),
    }
