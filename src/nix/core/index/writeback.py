"""Reindexação write-through de um único arquivo após escrita via ferramentas (RN-02)."""

from __future__ import annotations

from pathlib import Path

from nix.core.errors import VaultError
from nix.core.index.sync import Indexer, file_id_for
from nix.core.models import FileMeta, WriteResult
from nix.core.vault.paths import to_posix
from nix.observability.logging import get_logger

logger = get_logger("nix.index.writeback")


class Writeback:
    def __init__(self, indexer: Indexer) -> None:
        self._indexer = indexer

    def after_write(self, result: WriteResult) -> WriteResult:
        if not self._indexer.config.index.auto_index_agent_writes:
            return result
        rel = to_posix(result.rel_path)
        if result.action == "deleted":
            fid = file_id_for(rel)
            self._indexer.vectors.delete_file(fid)
            self._indexer.store.delete_file(fid)
            self._indexer.notify_change()
            return WriteResult(
                rel_path=rel,
                action=result.action,
                chunks_indexed=0,
                indexed=True,
                backup_path=result.backup_path,
                message=result.message + " Removida do índice.",
            )
        try:
            path = self._indexer.reader.resolve(rel)
            if not path.is_file():
                raise VaultError(
                    f"{rel} desapareceu após a escrita. "
                    "Verifique permissões ou antivírus no vault e rode `nix sync` "
                    "ou a ferramenta MCP `sync_index`."
                )
            stat = path.stat()
            n = self._indexer.index_file(
                FileMeta(rel_path=rel, mtime=stat.st_mtime, size_bytes=stat.st_size)
            )
            self._indexer.notify_change()
            return WriteResult(
                rel_path=rel,
                action=result.action,
                chunks_indexed=n,
                indexed=True,
                backup_path=result.backup_path,
                message=result.message + f" {n} chunks indexados.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Write-through falhou para %s", rel)
            path = Path(rel)
            try:
                resolved = self._indexer.reader.resolve(rel)
                st = resolved.stat() if resolved.exists() else None
                mtime = st.st_mtime if st else 0.0
                size = st.st_size if st else 0
            except Exception:  # noqa: BLE001
                mtime, size = 0.0, 0
            self._indexer.store.mark_error(file_id_for(rel), rel, mtime, size)
            return WriteResult(
                rel_path=rel,
                action=result.action,
                chunks_indexed=0,
                indexed=False,
                backup_path=result.backup_path,
                message=(
                    f"{result.message} A nota foi salva, mas não indexada ({exc}). "
                    "Rode `nix sync` ou a ferramenta MCP `sync_index` para corrigir o índice."
                ),
            )
