"""Operação: status, sincronização, diagnóstico e encerramento."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from nix.config.embedding_present import sync_model_hint
from nix.core.admin.doctor import DoctorCheck, DoctorReport, build_doctor_report
from nix.core.admin.traffic import TrafficCall, TrafficStore
from nix.core.errors import NixError
from nix.core.index.lock import mark_sync_job, unmark_sync_job
from nix.core.index.sync import combine_sync_reports
from nix.core.index.tokenize import approximate_tokenizer_hint
from nix.core.models import IndexStatus, SyncProgress, SyncReport
from nix.core.runtime import Runtime, VaultSpec
from nix.web.jobs import RuntimeGate, SyncJobs, SyncRun, launch_sync, vault_busy_message
from nix.web.render import fragment, page
from nix.web.routes.common import BUSY, Gated, form_data, is_hx, note, run_gated
from nix.web.state import ServerControl, WebState, web_state

_SHUTDOWN_BUSY = "Há uma sincronização em andamento. Espere ela terminar e clique em Encerrar de novo."
_PREVIEW_WAIT = "Há uma sincronização em andamento. Espere ela terminar e peça a prévia de novo."
_FULL = (
    "O nix sync --full recria o índice do zero. "
    'Marque "Confirmo a reindexação completa" para continuar.'
)
_ACTIONS = {
    "add": "adicionar",
    "update": "atualizar",
    "remove": "remover",
    "load_model": "carregar modelo",
}
_DOCTOR_BUSY = "Há uma sincronização em andamento. Espere ela terminar e atualize o diagnóstico."
_LEVEL_ORDER = ("error", "warn", "ok")
_TRIGGERS = {"manual": "manual", "writeback": "write-through"}


@dataclass(frozen=True)
class SyncRunView:
    started_at: str
    trigger: str
    added: int
    updated: int
    removed: int
    failed: int
    seconds: float | None
    errors: list[str]


@dataclass(frozen=True)
class Overview:
    status: IndexStatus
    runs: list[SyncRunView]


@dataclass(frozen=True)
class SyncContext:
    model: str
    runs: list[SyncRunView]


async def status_page(request: Request) -> Response:
    result = await run_gated(request, _overview)
    calls = await asyncio.to_thread(_recent_calls)
    overview = result.value
    return page(
        request,
        "status.html",
        {
            "title": "Status",
            "active": "status",
            "notice": result.notice,
            "error": result.error,
            "status": overview.status if overview else None,
            "runs": overview.runs if overview else [],
            "calls": calls,
            "settings_path": _settings_path(web_state(request).gate),
        },
    )


async def sync_page(request: Request) -> Response:
    state = web_state(request)
    result = await run_gated(request, _sync_context)
    model = result.value.model if result.value else state.gate.host.config.index.embedding_model
    return page(
        request,
        "sync.html",
        {
            "title": "Sincronizar",
            "active": "sync",
            "notice": result.notice,
            "error": result.error if not state.jobs.running() else None,
            "hint": sync_model_hint(model),
            "model": model,
            "running": state.jobs.running(),
            "runs": result.value.runs if result.value else [],
        },
    )


async def sync_preview(request: Request) -> Response:
    state = web_state(request)
    form = await form_data(request)
    selected = form.get("vault") or ""
    all_vaults = form.get("all_vaults") == "on"
    if state.jobs.running():
        return _sync_conflict(request, state, _PREVIEW_WAIT, selected=selected, all_vaults=all_vaults)
    spec = _sync_spec(selected or None, all_vaults)
    result = await asyncio.to_thread(partial(_preview_many, state.gate, spec, state.jobs))
    if state.jobs.running():
        return _sync_conflict(request, state, _PREVIEW_WAIT, selected=selected, all_vaults=all_vaults)
    report = result.value
    context: dict[str, Any] = {
        "notice": result.notice,
        "error": result.error,
        "report": report,
        "summary": report.summary_pt() if report is not None else None,
        "errors": report.errors if report is not None else [],
        "tokenizer": approximate_tokenizer_hint() if report is not None and report.tokenizer_approximate else None,
    }
    if is_hx(request):
        return page(request, "sync_preview.html", context)
    context.update(title="Sincronizar", active="sync")
    return page(request, "sync_preview_page.html", context)


async def sync_start(request: Request) -> Response:
    state = web_state(request)
    form = await form_data(request)
    full = form.get("full", "") == "on"
    all_vaults = form.get("all_vaults") == "on"
    selected = form.get("vault") or ""
    if full and form.get("confirm_full", "") != "on":
        return note(request, _FULL, status_code=200, active="sync")
    run = state.jobs.begin(asyncio.get_running_loop())
    if run is None:
        return _sync_conflict(request, state, BUSY, selected=selected, all_vaults=all_vaults)
    run.selected_vault = selected
    run.all_vaults = all_vaults
    spec = _sync_spec(selected or None, all_vaults)
    _called, notice = await asyncio.to_thread(state.gate.try_before_call)
    model = state.gate.host.config.index.embedding_model
    launch_sync(state.jobs, state.gate, run, full=full, spec=spec)
    if is_hx(request):
        # O POST termina quando a thread começa. O fieldset segue desligado até o fim do SSE.
        body = fragment("sync_live.html", notice=notice, full=full)
        body += _controls_oob(state, model, running=True, selected_vault=selected, all_vaults=all_vaults)
        return HTMLResponse(body)
    return page(
        request,
        "sync_live_page.html",
        {
            "title": "Sincronizar",
            "active": "sync",
            "notice": notice,
            "full": full,
            "model": model,
            "running": True,
            "selected_vault": selected,
            "all_vaults": all_vaults,
        },
    )


async def sync_events(request: Request) -> EventSourceResponse:
    state = web_state(request)
    token = state.token
    model = state.gate.host.config.index.embedding_model
    run = state.jobs.current()
    if run is None:
        return EventSourceResponse(_idle(token, model))
    return EventSourceResponse(_follow(run, token, model))


async def doctor_page(request: Request) -> Response:
    report, notice = await asyncio.to_thread(_doctor_report, web_state(request).gate)
    if notice:
        report.checks.insert(0, DoctorCheck("Processo", "warn", notice))
    counts = {level: sum(1 for check in report.checks if check.level == level) for level in _LEVEL_ORDER}
    checks = sorted(report.checks, key=lambda check: _LEVEL_ORDER.index(check.level))
    return page(
        request,
        "doctor.html",
        {"title": "Diagnóstico", "active": "doctor", "report": report, "counts": counts, "checks": checks},
    )


async def shutdown(request: Request) -> Response:
    state = web_state(request)
    if state.jobs.running():
        return note(request, _SHUTDOWN_BUSY, status_code=409)
    background = BackgroundTask(_stop, state.server) if state.server is not None else None
    return page(
        request,
        "shutdown.html",
        {"title": "Encerrar", "active": ""},
        background=background,
    )


def _overview(runtime: Runtime) -> Overview:
    return Overview(status=runtime.status(), runs=_runs(runtime, 3))


def _sync_context(runtime: Runtime) -> SyncContext:
    return SyncContext(model=runtime.config.index.embedding_model, runs=_runs(runtime, 5))


def _preview_many(gate: RuntimeGate, spec: VaultSpec, jobs: SyncJobs) -> Gated[SyncReport]:
    """Dry-run de um vault por vez. A trava de cada um solta antes do próximo."""
    if jobs.running():
        return Gated(None, None, _PREVIEW_WAIT)
    notice = gate.before_call()
    try:
        selected = gate.host.vaults_for(spec)
    except NixError as exc:
        return Gated(None, notice, exc.message)
    reports: list[tuple[str, SyncReport]] = []
    for vault in selected:
        if jobs.running():
            return Gated(None, notice, _PREVIEW_WAIT)
        lock = gate.lock_for(vault.name)
        if not lock.acquire(blocking=False):
            reports.append((vault.name, SyncReport(failed=1, errors=[vault_busy_message(vault.name)])))
            continue
        try:
            mark_sync_job(vault.name)
            if jobs.running():
                return Gated(None, notice, _PREVIEW_WAIT)
            try:
                runtime = gate.host.resolve(vault.name)
                report = runtime.indexer.sync(dry_run=True, trigger="manual")
            except NixError as exc:
                report = SyncReport(failed=1, errors=[exc.message])
            reports.append((vault.name, report))
        finally:
            unmark_sync_job(vault.name)
            lock.release()
    if not reports:
        return Gated(None, notice, "Nenhum vault disponível para a prévia. Rode `nix vault list`.")
    return Gated(combine_sync_reports(reports), notice, None)


def _sync_conflict(
    request: Request,
    state: WebState,
    message: str,
    *,
    selected: str,
    all_vaults: bool,
) -> Response:
    """Aviso de job em andamento. Não substitui o progresso nem varre o vault."""
    if not is_hx(request):
        return note(request, message, status_code=409, active="sync")
    model = state.gate.host.config.index.embedding_model
    body = fragment("fragment_message.html", message=message)
    body += _controls_oob(
        state,
        model,
        running=True,
        selected_vault=selected,
        all_vaults=all_vaults,
    )
    return HTMLResponse(
        body,
        status_code=409,
        headers={
            "Cache-Control": "no-store",
            "HX-Retarget": "#sync-alert",
            "HX-Reswap": "innerHTML",
        },
    )


def _runs(runtime: Runtime, limit: int) -> list[SyncRunView]:
    return [_run_view(row) for row in runtime.store.recent_sync_runs(limit)]


def _run_view(row: sqlite3.Row) -> SyncRunView:
    started = str(row["started_at"])
    finished = row["finished_at"]
    return SyncRunView(
        started_at=started,
        trigger=_TRIGGERS.get(str(row["trigger"]), str(row["trigger"])),
        added=int(row["added"] or 0),
        updated=int(row["updated"] or 0),
        removed=int(row["removed"] or 0),
        failed=int(row["failed"] or 0),
        seconds=_seconds(started, str(finished)) if finished else None,
        errors=[line for line in str(row["error_log"] or "").splitlines() if line.strip()],
    )


def _seconds(start: str, end: str) -> float | None:
    try:
        first = datetime.fromisoformat(start.replace("Z", "+00:00"))
        last = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    if (first.tzinfo is None) != (last.tzinfo is None):
        return None
    return max((last - first).total_seconds(), 0.0)


def _recent_calls() -> list[TrafficCall]:
    """O card de atividade é secundário: sem leitura do tráfego, a página segue sem ele."""
    try:
        return TrafficStore().recent(6)
    except (sqlite3.Error, OSError):
        return []


def _doctor_report(gate: RuntimeGate) -> tuple[DoctorReport, str | None]:
    with gate.borrow("*") as borrowed:
        statuses: list[tuple[str, IndexStatus | None, str | None]] = []
        for runtime in borrowed.runtimes:
            try:
                statuses.append((runtime.vault.name, runtime.status(), None))
            except NixError as exc:
                statuses.append((runtime.vault.name, None, exc.message))
        for skip in borrowed.skipped:
            statuses.append((skip["vault"], None, skip["message"]))
        report = build_doctor_report(
            inspect_index=False,
            vault_statuses=statuses,
            index_problem=borrowed.error,
        )
        return report, borrowed.notice


def _sync_spec(vault: str | None, all_vaults: bool) -> VaultSpec:
    if all_vaults:
        return "*"
    if vault and vault.strip():
        return vault.strip()
    return None


def _settings_path(gate: RuntimeGate) -> str:
    path = gate.host.config.settings_path
    if path is None:
        return "—"
    return str(path)


def _stop(server: ServerControl) -> None:
    server.should_exit = True


def _progress_html(event: SyncProgress) -> str:
    total = event.total if event.total > 0 else 1
    return fragment(
        "sync_progress.html",
        current=event.current,
        total=event.total,
        percent=min(100, round(event.current * 100 / total)),
        rel_path=event.rel_path,
        action=_ACTIONS.get(event.action, event.action),
        detail=event.detail,
        vault=event.vault,
    )


def _controls_oob(
    state: WebState,
    model: str,
    *,
    running: bool,
    selected_vault: str = "",
    all_vaults: bool = False,
) -> str:
    """`#sync-controls` para o HTMX trocar fora de banda, igual ao da página."""
    return fragment(
        "sync_controls.html",
        running=running,
        oob=True,
        csrf_token=state.token,
        model=model,
        selected_vault=selected_vault,
        all_vaults=all_vaults,
    )


def _done_html(
    *,
    csrf_token: str,
    model: str,
    report: SyncReport | None = None,
    error: str | None = None,
    selected_vault: str = "",
    all_vaults: bool = False,
) -> str:
    tokenizer = approximate_tokenizer_hint() if report is not None and report.tokenizer_approximate else None
    return fragment(
        "sync_done.html",
        report=report,
        summary=report.summary_pt() if report is not None else None,
        errors=report.errors if report is not None else [],
        error=error,
        tokenizer=tokenizer,
        csrf_token=csrf_token,
        model=model,
        running=False,
        oob=True,
        selected_vault=selected_vault,
        all_vaults=all_vaults,
    )


def _outcome_html(
    item: SyncReport | NixError,
    *,
    csrf_token: str,
    model: str,
    selected_vault: str,
    all_vaults: bool,
) -> str:
    if isinstance(item, NixError):
        return _done_html(
            csrf_token=csrf_token,
            model=model,
            error=item.message,
            selected_vault=selected_vault,
            all_vaults=all_vaults,
        )
    return _done_html(
        csrf_token=csrf_token,
        model=model,
        report=item,
        selected_vault=selected_vault,
        all_vaults=all_vaults,
    )


async def _follow(run: SyncRun, csrf_token: str, model: str) -> AsyncIterator[dict[str, str]]:
    async for item in run.iter_items():
        if isinstance(item, SyncProgress):
            yield {"event": "progress", "data": _progress_html(item)}
            continue
        html = _outcome_html(
            item,
            csrf_token=csrf_token,
            model=model,
            selected_vault=run.selected_vault,
            all_vaults=run.all_vaults,
        )
        # sse-swap só troca o evento progress; done fecha a conexão e leva o mesmo resumo.
        yield {"event": "progress", "data": html}
        yield {"event": "done", "data": html}
        return
    html = _done_html(
        csrf_token=csrf_token,
        model=model,
        error="A sincronização terminou sem um resultado. Rode `nix sync` de novo.",
        selected_vault=run.selected_vault,
        all_vaults=run.all_vaults,
    )
    yield {"event": "progress", "data": html}
    yield {"event": "done", "data": html}


async def _idle(csrf_token: str, model: str) -> AsyncIterator[dict[str, str]]:
    html = _done_html(csrf_token=csrf_token, model=model, error="Nenhuma sincronização em andamento.")
    yield {"event": "progress", "data": html}
    yield {"event": "done", "data": html}
