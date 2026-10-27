"""Ferramentas de manutenção do índice e insights do vault."""

from __future__ import annotations

from typing import Literal, assert_never

from pydantic import BaseModel, Field

from nix.core.errors import NixError
from nix.core.index.sync import json_safe
from nix.core.insights import InsightsService
from nix.core.runtime import Runtime
from nix.core.tools.args import MultiVaultArgs, VaultArgs

InsightKind = Literal["orphans", "duplicates", "links", "summary"]


class SyncIndexArgs(MultiVaultArgs):
    full: bool = False
    dry_run: bool = False


class IndexStatusArgs(MultiVaultArgs):
    pass


class InsightsArgs(VaultArgs):
    kind: InsightKind = Field(description="orphans, duplicates, links ou summary")
    limit: int = Field(default=20, ge=1, le=100)


class RememberArgs(VaultArgs):
    content: str = Field(description="Fato duradouro a persistir no vault")
    title: str | None = None


def sync_index(runtimes: list[Runtime], args: SyncIndexArgs) -> dict[str, object]:
    """Sincroniza um vault de cada vez e devolve o relatório de cada um."""
    reports: list[dict[str, object]] = []
    for runtime in runtimes:
        try:
            report = runtime.indexer.sync(full=args.full, dry_run=args.dry_run, trigger="manual")
        except NixError as exc:
            reports.append({"vault": runtime.vault.name, "error": exc.message})
            continue
        payload = json_safe(report)
        payload["vault"] = runtime.vault.name
        reports.append(payload)
    return {"vault": [runtime.vault.name for runtime in runtimes], "reports": reports}


def index_status(runtimes: list[Runtime], args: IndexStatusArgs) -> dict[str, object]:
    del args
    vaults: list[dict[str, object]] = []
    for runtime in runtimes:
        status = runtime.status()
        vaults.append(
            {
                "vault": runtime.vault.name,
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
        )
    return {"vault": [runtime.vault.name for runtime in runtimes], "vaults": vaults}


class ListVaultsArgs(BaseModel):
    """Sem parâmetros: a lista é sempre a dos vaults cadastrados."""


def list_vaults(runtimes: list[Runtime], args: ListVaultsArgs) -> dict[str, object]:
    """Nome, caminho, padrão e se o índice daquele vault está desatualizado."""
    del args
    items: list[dict[str, object]] = []
    for runtime in runtimes:
        try:
            stale = runtime.status().stale
            stale_error: str | None = None
        except NixError as exc:
            stale = True
            stale_error = exc.message
        item: dict[str, object] = {
            "vault": runtime.vault.name,
            "name": runtime.vault.name,
            "path": runtime.vault.path,
            "is_default": runtime.vault.is_default,
            "stale": stale,
        }
        if stale_error is not None:
            item["error"] = stale_error
        items.append(item)
    return {"vault": [runtime.vault.name for runtime in runtimes], "vaults": items}


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
