"""nix sync e nix status."""

from __future__ import annotations

import json

import typer
from rich.progress import Progress

from nix.cli.deps import get_runtime, with_errors
from nix.cli.render import apply_sync_progress, console, print_status
from nix.core.index.sync import json_safe
from nix.core.models import IndexStatus
from nix.core.models import SyncProgress as SyncProgressEvent
from nix.core.tools.registry import call_tool


def _status_from_payload(payload: object) -> IndexStatus:
    data = payload if isinstance(payload, dict) else {}
    return IndexStatus(
        files=int(data.get("files") or 0),
        chunks=int(data.get("chunks") or 0),
        errors=int(data.get("errors") or 0),
        last_sync_at=data.get("last_sync_at") if isinstance(data.get("last_sync_at"), str) else None,
        embedding_model=(
            data.get("embedding_model") if isinstance(data.get("embedding_model"), str) else None
        ),
        vault_path=data.get("vault_path") if isinstance(data.get("vault_path"), str) else None,
        stale=bool(data.get("stale")),
        stale_reason=(
            data.get("stale_reason") if isinstance(data.get("stale_reason"), str) else None
        ),
        data_dir=str(data.get("data_dir") or ""),
    )


@with_errors
def cmd_sync(
    full: bool = typer.Option(False, "--full", help="Reconstrói o índice inteiro"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que mudaria"),
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
) -> None:
    runtime = get_runtime()
    events: list[SyncProgressEvent] = []

    def on_progress(event: SyncProgressEvent) -> None:
        events.append(event)
        apply_sync_progress(progress, event)

    with Progress(console=console) as progress:
        progress.add_task("Sincronizando", total=1)
        report = runtime.indexer.sync(full=full, dry_run=dry_run, progress=on_progress)
    runtime.close()
    if as_json:
        console.print_json(json.dumps(json_safe(report), ensure_ascii=False))
        return
    prefix = "Pré-visualização: " if dry_run else ""
    console.print(prefix + report.summary_pt())
    for err in report.errors:
        console.print(f"[red]{err}[/red]")


@with_errors
def cmd_status(
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    runtime = get_runtime()
    payload = call_tool(runtime, "index_status", {})
    runtime.close()
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    print_status(_status_from_payload(payload))
