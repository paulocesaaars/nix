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
from nix.core.index.tokenize import approximate_tokenizer_hint
from nix.core.models import IndexStatus, SyncProgress, SyncReport
from nix.core.runtime import Runtime
from nix.web.jobs import RuntimeGate, SyncRun, launch_sync
from nix.web.render import fragment, page
from nix.web.routes.common import BUSY, form_data, is_hx, note, run_gated
from nix.web.state import ServerControl, web_state

_SHUTDOWN_BUSY = "Há uma sincronização em andamento. Espere ela terminar e clique em Encerrar de novo."
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
    model = result.value.model if result.value else state.gate.host.runtime.config.index.embedding_model
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
    result = await run_gated(request, _preview)
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
    if full and form.get("confirm_full", "") != "on":
        return note(request, _FULL, status_code=200, active="sync")
    run = state.jobs.begin(asyncio.get_running_loop())
    if run is None:
        return note(request, BUSY, status_code=409, active="sync")
    _called, notice = await asyncio.to_thread(state.gate.try_before_call)
    launch_sync(state.jobs, state.gate, run, full=full)
    if is_hx(request):
        return HTMLResponse(fragment("sync_live.html", notice=notice, full=full))
    return page(
        request,
        "sync_live_page.html",
        {"title": "Sincronizar", "active": "sync", "notice": notice, "full": full},
    )


async def sync_events(request: Request) -> EventSourceResponse:
    run = web_state(request).jobs.current()
    if run is None:
        return EventSourceResponse(_idle())
    return EventSourceResponse(_follow(run))


async def doctor_page(request: Request) -> Response:
    result = await run_gated(request, _doctor_report, busy=_DOCTOR_BUSY)
    report = result.value
    if report is None:
        report = await asyncio.to_thread(
            partial(build_doctor_report, inspect_index=False, index_problem=result.error)
        )
    if result.notice:
        report.checks.insert(0, DoctorCheck("Processo", "warn", result.notice))
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


def _preview(runtime: Runtime) -> SyncReport:
    return runtime.indexer.sync(dry_run=True, trigger="manual")


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


def _doctor_report(runtime: Runtime) -> DoctorReport:
    try:
        status = runtime.status()
    except NixError as exc:
        return build_doctor_report(inspect_index=False, index_problem=exc.message)
    return build_doctor_report(inspect_index=False, index_status=status)


def _settings_path(gate: RuntimeGate) -> str:
    path = gate.host.runtime.config.settings_path
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
    )


def _done_html(*, report: SyncReport | None = None, error: str | None = None) -> str:
    tokenizer = approximate_tokenizer_hint() if report is not None and report.tokenizer_approximate else None
    return fragment(
        "sync_done.html",
        report=report,
        summary=report.summary_pt() if report is not None else None,
        errors=report.errors if report is not None else [],
        error=error,
        tokenizer=tokenizer,
    )


def _outcome_html(item: SyncReport | NixError) -> str:
    if isinstance(item, NixError):
        return _done_html(error=item.message)
    return _done_html(report=item)


async def _follow(run: SyncRun) -> AsyncIterator[dict[str, str]]:
    async for item in run.iter_items():
        if isinstance(item, SyncProgress):
            yield {"event": "progress", "data": _progress_html(item)}
            continue
        html = _outcome_html(item)
        # sse-swap só troca o evento progress; done fecha a conexão e leva o mesmo resumo.
        yield {"event": "progress", "data": html}
        yield {"event": "done", "data": html}
        return
    yield {
        "event": "done",
        "data": _done_html(error="A sincronização terminou sem um resultado. Rode `nix sync` de novo."),
    }


async def _idle() -> AsyncIterator[dict[str, str]]:
    yield {"event": "done", "data": _done_html(error="Nenhuma sincronização em andamento.")}
