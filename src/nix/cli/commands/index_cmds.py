"""nix sync e nix status."""

from __future__ import annotations

import json

import typer

from nix.cli.deps import get_host, with_errors
from nix.cli.render import (
    apply_sync_progress,
    console,
    print_status,
    print_tokenizer_warning,
    sync_progress,
)
from nix.config.embedding_present import sync_model_hint
from nix.core.errors import ConfigError, NixError
from nix.core.index.sync import combine_sync_reports, json_safe
from nix.core.models import IndexStatus, SyncReport
from nix.core.models import SyncProgress as SyncProgressEvent
from nix.core.tools.registry import call_tool


def _status_from_payload(payload: object) -> IndexStatus:
    data = payload if isinstance(payload, dict) else {}
    return IndexStatus(
        files=int(data.get("files") or 0),
        sessions=int(data.get("sessions") or 0),
        chunks=int(data.get("chunks") or 0),
        errors=int(data.get("errors") or 0),
        last_sync_at=data.get("last_sync_at") if isinstance(data.get("last_sync_at"), str) else None,
        embedding_model=(data.get("embedding_model") if isinstance(data.get("embedding_model"), str) else None),
        vault_path=data.get("vault_path") if isinstance(data.get("vault_path"), str) else None,
        stale=bool(data.get("stale")),
        stale_reason=(data.get("stale_reason") if isinstance(data.get("stale_reason"), str) else None),
        data_dir=str(data.get("data_dir") or ""),
    )


def _vault_spec(vault: list[str] | None, all_vaults: bool) -> str | list[str] | None:
    names = [item.strip() for item in (vault or []) if item.strip()]
    if all_vaults and names:
        raise ConfigError(
            "Use `--all` ou `--vault NOME`, não os dois. Omita os dois para usar só o vault padrão."
        )
    if all_vaults:
        return "*"
    if names:
        return names
    return None


@with_errors
def cmd_sync(
    full: bool = typer.Option(False, "--full", help="Reconstrói o índice inteiro"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que mudaria"),
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
    vault: list[str] | None = typer.Option(None, "--vault", help="Nome do vault. Repita para vários."),
    all_vaults: bool = typer.Option(False, "--all", help="Sincroniza todos os vaults, em sequência."),
) -> None:
    host = get_host(capture_embedder_stdout=as_json)
    spec = _vault_spec(vault, all_vaults)
    events: list[SyncProgressEvent] = []
    reports: list[tuple[str, SyncReport]] = []
    failures: list[str] = []
    try:
        opened = host.resolve_many(spec)
        for failure in opened.errors:
            failures.append(f"{failure.name}: {failure.message}")
        runtimes = opened.runtimes
        if not dry_run and not as_json and runtimes:
            console.print(f"[dim]{sync_model_hint(runtimes[0].config.index.embedding_model)}[/dim]")
        with sync_progress() as progress:
            progress.add_task("Sincronizando", total=1)
            for runtime in runtimes:
                events.clear()

                def on_progress(event: SyncProgressEvent) -> None:
                    events.append(event)
                    apply_sync_progress(progress, event)

                try:
                    report = runtime.indexer.sync(full=full, dry_run=dry_run, progress=on_progress)
                except NixError as exc:
                    failures.append(f"{runtime.vault.name}: {exc.message}")
                    continue
                report.vault_name = runtime.vault.name
                reports.append((runtime.vault.name, report))
                if not as_json:
                    _print_sync(
                        runtime.vault.name,
                        runtime.vault.root,
                        list(runtime.vault.exclude),
                        report,
                        events,
                        dry_run,
                    )
    finally:
        host.close()
    combined = combine_sync_reports(reports)
    if as_json:
        payload = {
            "vault": [name for name, _report in reports],
            "reports": [{**json_safe(report), "vault": name} for name, report in reports],
            "vault_errors": failures,
            "summary": combined.summary_pt() if reports else "",
        }
        console.print_json(json.dumps(payload, ensure_ascii=False))
    if failures:
        detail = " ".join(failures)
        raise ConfigError(f"A sincronização falhou em algum vault. {detail}")


def _print_sync(
    name: str,
    root: object,
    excludes: list[str],
    report: SyncReport,
    events: list[SyncProgressEvent],
    dry_run: bool,
) -> None:
    prefix = "Pré-visualização: " if dry_run else ""
    console.print(prefix + report.summary_pt())
    print_tokenizer_warning(approximate=report.tokenizer_approximate)
    console.print(f"Vault {name}: {root}")
    processed = [event for event in events if event.action != "load_model"]
    if processed:
        console.print("Arquivos:")
        for event in processed:
            label = f"{event.vault} " if event.vault else ""
            console.print(f"  {label}{event.action} {event.rel_path}")
    if excludes:
        console.print(f"[dim]Pastas ignoradas (vault.exclude): {', '.join(excludes)}[/dim]")
    for err in report.errors:
        console.print(f"[red]{err}[/red]")


@with_errors
def cmd_status(
    as_json: bool = typer.Option(False, "--json"),
    vault: list[str] | None = typer.Option(None, "--vault", help="Nome do vault. Repita para vários."),
    all_vaults: bool = typer.Option(False, "--all", help="Mostra o estado de todos os vaults."),
) -> None:
    host = get_host()
    spec = _vault_spec(vault, all_vaults)
    try:
        payload = call_tool(host, "index_status", {"vault": spec} if spec is not None else {})
    finally:
        host.close()
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    rows = payload.get("vaults") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        print_status(_status_from_payload(payload))
        return
    for item in rows:
        if isinstance(item, dict):
            title = str(item.get("vault") or "")
            if title:
                console.print(f"[bold]{title}[/bold]")
            print_status(_status_from_payload(item))
