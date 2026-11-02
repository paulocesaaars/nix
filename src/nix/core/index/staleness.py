"""Detecção barata de defasagem entre wiki e índice (sem reindexar)."""

from __future__ import annotations

from nix.core.index.store import IndexStore
from nix.core.models import FileMeta, IndexStatus
from nix.core.wiki.reader import WikiReader


def compute_status(
    store: IndexStore,
    reader: WikiReader,
    *,
    data_dir: str = "",
    warn_when_stale: bool = True,
    wiki_name: str = "",
    sessions_folder: str | None = None,
) -> IndexStatus:
    last_sync = store.get_meta("last_sync_at")
    embedding = store.get_meta("embedding_model")
    # `vault_path` é a chave gravada por versões anteriores. Não reescrevemos o índice na migração.
    wiki_path = store.get_meta("wiki_path") or store.get_meta("vault_path")
    indexed = store.indexed_markdown_stats()
    indexed_files = len(indexed)
    sessions = store.count_markdown_under(sessions_folder) if sessions_folder else 0
    errors = store.count_files("error")
    chunks = store.count_chunks()
    on_disk = list(reader.iter_markdown())
    wiki_count = len(on_disk)
    stale = False
    reason: str | None = None
    sync_hint = f"`nix sync --wiki {wiki_name}`" if wiki_name else "`nix sync`"
    if last_sync is None:
        stale = True
        reason = f"O índice nunca foi sincronizado. Rode {sync_hint} ou a ferramenta `sync_index`."
    elif wiki_count != indexed_files:
        stale = True
        reason = (
            f"A wiki tem {wiki_count} notas Markdown visíveis e o índice tem {indexed_files}. "
            f"Rode {sync_hint} ou a ferramenta `sync_index` para alinhar "
            "(nenhuma indexação automática será feita)."
        )
    elif _markdown_drift(on_disk, indexed):
        stale = True
        reason = (
            "Há notas na wiki diferentes da versão indexada. "
            f"Rode {sync_hint} ou a ferramenta `sync_index` se quiser incluir "
            "as edições feitas fora do Nix."
        )
    if not warn_when_stale:
        reason = None
    return IndexStatus(
        files=indexed_files - sessions,
        chunks=chunks,
        errors=errors,
        last_sync_at=last_sync,
        embedding_model=embedding,
        wiki_path=wiki_path,
        stale=stale,
        stale_reason=reason,
        data_dir=data_dir,
        sessions=sessions,
    )


def _markdown_drift(on_disk: list[FileMeta], indexed: dict[str, tuple[float, int]]) -> bool:
    """Nota fora do índice, ou com mtime/tamanho diferentes da linha indexada.

    O write-through grava o mtime e o tamanho da escrita. Enquanto o arquivo
    continuar igual, a nota não fica desatualizada — mesmo que seja mais nova
    que `last_sync_at`.
    """
    seen: set[str] = set()
    for meta in on_disk:
        seen.add(meta.rel_path)
        known = indexed.get(meta.rel_path)
        if known is None or known != (meta.mtime, meta.size_bytes):
            return True
    return len(seen) != len(indexed)
