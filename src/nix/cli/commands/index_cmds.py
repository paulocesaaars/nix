"""nix sync e nix status."""

from __future__ import annotations

import json

import typer

from nix.cli.deps import get_host, with_errors
from nix.cli.render import (
    apply_sync_progress,
    console,
    print_header,
    print_status,
    print_sync_report,
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
        wiki_path=data.get("wiki_path") if isinstance(data.get("wiki_path"), str) else None,
        stale=bool(data.get("stale")),
        stale_reason=(data.get("stale_reason") if isinstance(data.get("stale_reason"), str) else None),
        data_dir=str(data.get("data_dir") or ""),
    )


def _wiki_spec(wiki: list[str] | None, all_wikis: bool) -> str | list[str] | None:
    names = [item.strip() for item in (wiki or []) if item.strip()]
    if all_wikis and names:
        raise ConfigError(
            "Use `--all` ou `--wiki NOME`, não os dois. Omita os dois para usar só a wiki padrão."
        )
    if all_wikis:
        return "*"
    if names:
        return names
    return None


@with_errors
def cmd_sync(
    full: bool = typer.Option(False, "--full", help="Reconstrói o índice inteiro"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que mudaria"),
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
    wiki: list[str] | None = typer.Option(None, "--wiki", help="Nome da wiki. Repita para vários."),
    all_wikis: bool = typer.Option(False, "--all", help="Sincroniza todas as wikis, em sequência."),
) -> None:
    host = get_host(capture_embedder_stdout=as_json)
    spec = _wiki_spec(wiki, all_wikis)
    events: list[SyncProgressEvent] = []
    reports: list[tuple[str, SyncReport]] = []
    failures: list[str] = []
    try:
        opened = host.resolve_many(spec)
        for failure in opened.errors:
            failures.append(f"{failure.name}: {failure.message}")
        runtimes = opened.runtimes
        if not as_json:
            print_header("prévia da sincronização" if dry_run else "sincronização")
        if not dry_run and not as_json and runtimes:
            console.print(f" [dim]{sync_model_hint(runtimes[0].config.index.embedding_model)}[/dim]")
            console.print()
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
                    failures.append(f"{runtime.wiki.name}: {exc.message}")
                    continue
                report.wiki_name = runtime.wiki.name
                reports.append((runtime.wiki.name, report))
                if not as_json:
                    print_sync_report(
                        runtime.wiki.name,
                        runtime.wiki.root,
                        list(runtime.wiki.exclude),
                        report,
                        events,
                        dry_run,
                    )
    finally:
        host.close()
    combined = combine_sync_reports(reports)
    if as_json:
        payload = {
            "wiki": [name for name, _report in reports],
            "reports": [{**json_safe(report), "wiki": name} for name, report in reports],
            "wiki_errors": failures,
            "summary": combined.summary_pt() if reports else "",
        }
        console.print_json(json.dumps(payload, ensure_ascii=False))
    if failures:
        detail = " ".join(failures)
        raise ConfigError(f"A sincronização falhou em alguma wiki. {detail}")


@with_errors
def cmd_status(
    as_json: bool = typer.Option(False, "--json"),
    wiki: list[str] | None = typer.Option(None, "--wiki", help="Nome da wiki. Repita para vários."),
    all_wikis: bool = typer.Option(False, "--all", help="Mostra o estado de todas as wikis."),
) -> None:
    host = get_host()
    spec = _wiki_spec(wiki, all_wikis)
    try:
        payload = call_tool(host, "index_status", {"wiki": spec} if spec is not None else {})
    finally:
        host.close()
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    rows = payload.get("wikis") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        print_header()
        print_status(_status_from_payload(payload))
        return
    print_header()
    for item in rows:
        if isinstance(item, dict):
            print_status(_status_from_payload(item), wiki=str(item.get("wiki") or "") or None)
