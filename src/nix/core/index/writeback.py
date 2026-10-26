"""Reindexação write-through de um único arquivo após escrita via ferramentas (RN-02)."""

from __future__ import annotations

from nix.core.errors import VaultError
from nix.core.index.lock import index_lock
from nix.core.index.sync import Indexer, file_id_for
from nix.core.models import FileMeta, WriteResult
from nix.core.vault.paths import to_posix
from nix.observability.logging import get_logger

logger = get_logger("nix.index.writeback")


class Writeback:
    def __init__(self, indexer: Indexer) -> None:
        self._indexer = indexer

    def after_write(self, result: WriteResult) -> WriteResult:
        if not result.written or not self._indexer.config.index.auto_index_agent_writes:
            return result
        with index_lock():
            return self._after_write(result)

    def after_move(self, result: WriteResult) -> WriteResult:
        if not self._indexer.config.index.auto_index_agent_writes:
            return result
        with index_lock():
            return self._after_move(result)

    def _after_write(self, result: WriteResult) -> WriteResult:
        if not result.written:
            return result
        if not self._indexer.config.index.auto_index_agent_writes:
            return result
        rel = to_posix(result.rel_path)
        if result.action == "deleted":
            fid = file_id_for(rel)
            self._indexer.vectors.delete_file(fid)
            self._indexer.store.delete_file(fid)
            self._indexer.notify_change()
            return self._finish(
                result,
                rel=rel,
                chunks=0,
                indexed=True,
                message=result.message + " Removida do índice.",
            )
        chunks, error = self._index_path(rel)
        self._indexer.notify_change()
        if error:
            return self._finish(
                result,
                rel=rel,
                chunks=0,
                indexed=False,
                message=(
                    f"{result.message} A nota foi salva, mas não indexada ({error}). "
                    "Rode `nix sync` ou a ferramenta MCP `sync_index` para corrigir o índice."
                ),
            )
        return self._finish(
            result,
            rel=rel,
            chunks=chunks,
            indexed=True,
            message=result.message + f" {chunks} chunks indexados.",
        )

    def _after_move(self, result: WriteResult) -> WriteResult:
        """Tira o id antigo do índice, indexa o caminho novo e as notas com links reescritos."""
        if not self._indexer.config.index.auto_index_agent_writes:
            return result
        old = to_posix(result.moved_from) if result.moved_from else ""
        new = to_posix(result.rel_path)
        if old:
            fid = file_id_for(old)
            self._indexer.vectors.delete_file(fid)
            self._indexer.store.delete_file(fid)
        total = 0
        errors: list[str] = []
        if self._should_index(new):
            chunks, error = self._index_path(new)
            total += chunks
            if error:
                errors.append(f"{new}: {error}")
        for rel in result.links_updated:
            rel_n = to_posix(rel)
            if rel_n == new:
                continue
            chunks, error = self._index_path(rel_n)
            total += chunks
            if error:
                errors.append(f"{rel_n}: {error}")
        self._indexer.notify_change()
        if errors:
            detail = "; ".join(errors)
            return self._finish(
                result,
                rel=new,
                chunks=total,
                indexed=False,
                message=(
                    f"{result.message} A movimentação foi salva, mas parte do índice falhou ({detail}). "
                    "Rode `nix sync` ou a ferramenta MCP `sync_index` para corrigir o índice."
                ),
            )
        return self._finish(
            result,
            rel=new,
            chunks=total,
            indexed=True,
            message=result.message + f" {total} chunks indexados.",
        )

    def _should_index(self, rel: str) -> bool:
        lowered = rel.lower()
        if lowered.endswith(".md"):
            return True
        return lowered.endswith(".pdf") and self._indexer.config.index.index_attachments

    def _index_path(self, rel: str) -> tuple[int, str | None]:
        try:
            path = self._indexer.reader.resolve(rel)
            if not path.is_file():
                raise VaultError(
                    f"{rel} não está no vault após a operação. "
                    "Verifique permissões ou antivírus no vault e rode `nix sync` "
                    "ou a ferramenta MCP `sync_index`."
                )
            stat = path.stat()
            count = self._indexer.index_file(
                FileMeta(rel_path=rel, mtime=stat.st_mtime, size_bytes=stat.st_size)
            )
            return count, None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Write-through falhou para %s", rel)
            try:
                resolved = self._indexer.reader.resolve(rel)
                st = resolved.stat() if resolved.exists() else None
                mtime = st.st_mtime if st else 0.0
                size = st.st_size if st else 0
            except Exception:  # noqa: BLE001
                mtime, size = 0.0, 0
            self._indexer.store.mark_error(file_id_for(rel), rel, mtime, size)
            return 0, str(exc)

    def _finish(
        self,
        result: WriteResult,
        *,
        rel: str,
        chunks: int,
        indexed: bool,
        message: str,
    ) -> WriteResult:
        return WriteResult(
            rel_path=rel,
            action=result.action,
            chunks_indexed=chunks,
            indexed=indexed,
            backup_path=result.backup_path,
            message=message,
            moved_from=result.moved_from,
            links_updated=list(result.links_updated),
            links_pending=list(result.links_pending),
            written=result.written,
        )
