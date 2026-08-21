"""Ferramentas de manutenção do índice e insights do vault."""

from __future__ import annotations

from typing import Literal, assert_never

from pydantic import BaseModel, Field

from nix.core.index.sync import json_safe
from nix.core.insights import InsightsService
from nix.core.runtime import Runtime

InsightKind = Literal["orphans", "duplicates", "links", "summary"]


class SyncIndexArgs(BaseModel):
    full: bool = False
    dry_run: bool = False


class IndexStatusArgs(BaseModel):
    pass


class InsightsArgs(BaseModel):
    kind: InsightKind = Field(description="orphans, duplicates, links ou summary")
    limit: int = Field(default=20, ge=1, le=100)


class RememberArgs(BaseModel):
    content: str = Field(description="Fato duradouro a persistir no vault")
    title: str | None = None


def sync_index(runtime: Runtime, args: SyncIndexArgs) -> dict[str, object]:
    report = runtime.indexer.sync(full=args.full, dry_run=args.dry_run, trigger="manual")
    return json_safe(report)


def index_status(runtime: Runtime, args: IndexStatusArgs) -> dict[str, object]:
    del args
    status = runtime.status()
    return {
        "files": status.files,
        "chunks": status.chunks,
        "errors": status.errors,
        "last_sync_at": status.last_sync_at,
        "embedding_model": status.embedding_model,
        "vault_path": status.vault_path,
        "stale": status.stale,
        "stale_reason": status.stale_reason,
        "data_dir": status.data_dir,
    }


def vault_insights(runtime: Runtime, args: InsightsArgs) -> dict[str, object]:
    svc = InsightsService(runtime.store, runtime.graph)
    if args.kind == "orphans":
        return {"kind": "orphans", "items": [i.__dict__ for i in svc.orphans()[: args.limit]]}
    if args.kind == "duplicates":
        return {
            "kind": "duplicates",
            "items": [i.__dict__ for i in svc.duplicates()[: args.limit]],
        }
    if args.kind == "links":
        return {"kind": "links", "items": [i.__dict__ for i in svc.suggest_links(args.limit)]}
    if args.kind == "summary":
        return {"kind": "summary", "items": svc.summary()}
    assert_never(args.kind)


def remember(runtime: Runtime, args: RememberArgs) -> dict[str, object]:
    from nix.core.vault.longterm import persist_memory

    return persist_memory(runtime, args.content, title=args.title)
