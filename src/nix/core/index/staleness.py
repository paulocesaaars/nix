"""Detecção barata de defasagem entre vault e índice (sem reindexar)."""

from __future__ import annotations

from datetime import UTC, datetime

from nix.core.index.store import IndexStore
from nix.core.models import IndexStatus
from nix.core.vault.reader import VaultReader


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def compute_status(
    store: IndexStore,
    reader: VaultReader,
    *,
    data_dir: str = "",
    warn_when_stale: bool = True,
) -> IndexStatus:
    last_sync = store.get_meta("last_sync_at")
    embedding = store.get_meta("embedding_model")
    vault_path = store.get_meta("vault_path")
    indexed_files = store.count_markdown("indexed")
    errors = store.count_files("error")
    chunks = store.count_chunks()
    max_mtime, vault_count = reader.max_mtime_and_count()
    stale = False
    reason: str | None = None
    sync_dt = parse_iso(last_sync)
    if last_sync is None:
        stale = True
        reason = "O índice nunca foi sincronizado. Rode `nix sync` ou a ferramenta `sync_index`."
    elif vault_count != indexed_files:
        stale = True
        reason = (
            f"O vault tem {vault_count} notas Markdown visíveis e o índice tem {indexed_files}. "
            "Rode `nix sync` ou a ferramenta `sync_index` para alinhar "
            "(nenhuma indexação automática será feita)."
        )
    elif sync_dt is not None and max_mtime > sync_dt.timestamp() + 1:
        stale = True
        reason = (
            "Há arquivos no vault mais recentes que o último sync. "
            "Rode `nix sync` ou a ferramenta `sync_index` se quiser incluir "
            "as edições feitas no Obsidian."
        )
    if not warn_when_stale:
        reason = None
    return IndexStatus(
        files=indexed_files,
        chunks=chunks,
        errors=errors,
        last_sync_at=last_sync,
        embedding_model=embedding,
        vault_path=vault_path,
        stale=stale,
        stale_reason=reason,
        data_dir=data_dir,
    )
