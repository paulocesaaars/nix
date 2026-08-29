"""nix sync e nix status."""

from __future__ import annotations

import json

import typer

from nix.cli.deps import get_runtime, with_errors
from nix.cli.render import apply_sync_progress, console, print_status, sync_progress
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

    if not dry_run:
        console.print(
            "[dim]Sem GPU o embedding roda na CPU. O modelo padrão BAAI/bge-m3 "
            "pesa ~2,3 GB na primeira vez e cada nota pode levar minutos. "
            "A barra só avança quando o arquivo termina — não está travado.[/dim]"
        )
        console.print(
            "[dim]Em máquina fraca com notas em português, use no nix.toml "
            "index.embedding_model = "
            "\"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2\" "
            "e depois `nix sync --full`. Só inglês: all-MiniLM-L6-v2.[/dim]"
        )

    with sync_progress() as progress:
        progress.add_task("Sincronizando", total=1)
        report = runtime.indexer.sync(full=full, dry_run=dry_run, progress=on_progress)
    vault_root = runtime.config.vault.root
    excludes = list(runtime.config.vault.exclude)
    runtime.close()
    if as_json:
        console.print_json(json.dumps(json_safe(report), ensure_ascii=False))
        return
    prefix = "Pré-visualização: " if dry_run else ""
    console.print(prefix + report.summary_pt())
    console.print(f"Vault: {vault_root}")
    processed = [e for e in events if e.action != "load_model"]
    if processed:
        console.print("Arquivos:")
        for event in processed:
            console.print(f"  {event.action} {event.rel_path}")
    if excludes:
        console.print(f"[dim]Pastas ignoradas (vault.exclude): {', '.join(excludes)}[/dim]")
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
