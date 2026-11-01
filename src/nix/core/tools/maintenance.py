"""Ferramentas de manutenção do índice e insights da wiki."""

from __future__ import annotations

from typing import Literal, assert_never

from pydantic import BaseModel, Field

from nix.core.errors import NixError
from nix.core.index.sync import json_safe
from nix.core.insights import InsightsService
from nix.core.runtime import Runtime
from nix.core.tools.args import MultiWikiArgs, WikiArgs

InsightKind = Literal["orphans", "duplicates", "links", "summary"]


class SyncIndexArgs(MultiWikiArgs):
    full: bool = False
    dry_run: bool = False


class IndexStatusArgs(MultiWikiArgs):
    pass


class InsightsArgs(WikiArgs):
    kind: InsightKind = Field(description="orphans, duplicates, links ou summary")
    limit: int = Field(default=20, ge=1, le=100)


class RememberArgs(WikiArgs):
    content: str = Field(description="Fato duradouro a persistir na wiki")
    title: str | None = None


def sync_index(runtimes: list[Runtime], args: SyncIndexArgs) -> dict[str, object]:
    """Sincroniza uma wiki de cada vez e devolve o relatório de cada um."""
    reports: list[dict[str, object]] = []
    for runtime in runtimes:
        try:
            report = runtime.indexer.sync(full=args.full, dry_run=args.dry_run, trigger="manual")
        except NixError as exc:
            reports.append({"wiki": runtime.wiki.name, "error": exc.message})
            continue
        payload = json_safe(report)
        payload["wiki"] = runtime.wiki.name
        reports.append(payload)
    return {"wiki": [runtime.wiki.name for runtime in runtimes], "reports": reports}


def index_status(runtimes: list[Runtime], args: IndexStatusArgs) -> dict[str, object]:
    del args
    wikis: list[dict[str, object]] = []
    for runtime in runtimes:
        status = runtime.status()
        wikis.append(
            {
                "wiki": runtime.wiki.name,
                "files": status.files,
                "sessions": status.sessions,
                "chunks": status.chunks,
                "errors": status.errors,
                "last_sync_at": status.last_sync_at,
                "embedding_model": status.embedding_model,
                "wiki_path": status.wiki_path,
                "stale": status.stale,
                "stale_reason": status.stale_reason,
                "data_dir": status.data_dir,
            }
        )
    return {"wiki": [runtime.wiki.name for runtime in runtimes], "wikis": wikis}


class ListWikisArgs(BaseModel):
    """Sem parâmetros: a lista é sempre a das wikis cadastradas."""


def list_wikis(runtimes: list[Runtime], args: ListWikisArgs) -> dict[str, object]:
    """Nome, caminho, padrão e se o índice daquela wiki está desatualizado."""
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
            "wiki": runtime.wiki.name,
            "name": runtime.wiki.name,
            "path": runtime.wiki.path,
            "is_default": runtime.wiki.is_default,
            "stale": stale,
        }
        if stale_error is not None:
            item["error"] = stale_error
        items.append(item)
    return {"wiki": [runtime.wiki.name for runtime in runtimes], "wikis": items}


def wiki_insights(runtime: Runtime, args: InsightsArgs) -> dict[str, object]:
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
    from nix.core.wiki.longterm import persist_memory

    return persist_memory(runtime, args.content, title=args.title)
