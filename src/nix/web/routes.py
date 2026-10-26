"""Rotas da interface local."""

from __future__ import annotations

import asyncio
import json
import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from nix.config.editor import history, revert_change
from nix.config.embedding_present import sync_model_hint
from nix.core.admin.doctor import DoctorCheck, DoctorReport, build_doctor_report
from nix.core.errors import NixError
from nix.core.index.tokenize import approximate_tokenizer_hint
from nix.core.models import IndexStatus, SyncProgress, SyncReport
from nix.web.jobs import RuntimeGate, SyncRun, launch_sync
from nix.web.render import fragment, page
from nix.web.settings_form import apply_form, field_groups
from nix.web.state import ServerControl, web_state

_BUSY = "Já existe uma sincronização em andamento. Espere ela terminar."
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


@dataclass(frozen=True)
class HistoryView:
    id: int
    changed_at: str
    source: str
    dotted: str
    old_value: str
    new_value: str


def build_routes() -> list[BaseRoute]:
    static = Path(__file__).parent / "static"
    return [
        Route("/", status_page, methods=["GET"]),
        Route("/sync", sync_page, methods=["GET"]),
        Route("/sync/preview", sync_preview, methods=["POST"]),
        Route("/sync/start", sync_start, methods=["POST"]),
        Route("/sync/events", sync_events, methods=["GET"]),
        Route("/doctor", doctor_page, methods=["GET"]),
        Route("/settings", settings_page, methods=["GET"]),
        Route("/settings", settings_save, methods=["POST"]),
        Route("/history", history_page, methods=["GET"]),
        Route("/history/{change_id:int}/undo", history_undo, methods=["POST"]),
        Route("/shutdown", shutdown, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=static), name="static"),
    ]


async def status_page(request: Request) -> Response:
    state = web_state(request)
    notice, status, settings_path = await asyncio.to_thread(_read_status, state.gate)
    return page(
        request,
        "status.html",
        {"title": "Status", "active": "status", "notice": notice, "status": status, "settings_path": settings_path},
    )


async def sync_page(request: Request) -> Response:
    state = web_state(request)
    notice, model = await asyncio.to_thread(_sync_context, state.gate)
    return page(
        request,
        "sync.html",
        {
            "title": "Sincronizar",
            "active": "sync",
            "notice": notice,
            "hint": sync_model_hint(model),
            "running": state.jobs.running(),
        },
    )


async def sync_preview(request: Request) -> Response:
    state = web_state(request)
    notice, report, problem = await asyncio.to_thread(_preview, state.gate)
    context: dict[str, Any] = {
        "notice": notice,
        "error": problem,
        "summary": report.summary_pt() if report is not None else None,
        "errors": report.errors if report is not None else [],
        "tokenizer": approximate_tokenizer_hint() if report is not None and report.tokenizer_approximate else None,
    }
    if _hx(request):
        return page(request, "sync_preview.html", context)
    context.update(title="Sincronizar", active="sync")
    return page(request, "sync_preview_page.html", context)


async def sync_start(request: Request) -> Response:
    state = web_state(request)
    form = await _form(request)
    if form.get("full", "") == "on" and form.get("confirm_full", "") != "on":
        return _note(request, _FULL, status_code=200)
    run = state.jobs.begin(asyncio.get_running_loop())
    if run is None:
        return _note(request, _BUSY, status_code=409)
    _called, notice = await asyncio.to_thread(state.gate.try_before_call)
    launch_sync(state.jobs, state.gate, run, full=form.get("full", "") == "on")
    if _hx(request):
        return HTMLResponse(fragment("sync_live.html", notice=notice))
    return page(
        request,
        "sync_live_page.html",
        {"title": "Sincronizar", "active": "sync", "notice": notice},
    )


async def sync_events(request: Request) -> EventSourceResponse:
    run = web_state(request).jobs.current()
    if run is None:
        return EventSourceResponse(_idle())
    return EventSourceResponse(_follow(run))


async def doctor_page(request: Request) -> Response:
    try:
        report = await asyncio.to_thread(_doctor_report, web_state(request).gate)
    except NixError as exc:
        return page(
            request,
            "message.html",
            {"title": "Diagnóstico", "active": "doctor", "message": exc.message},
        )
    return page(request, "doctor.html", {"title": "Diagnóstico", "active": "doctor", "report": report})


async def settings_page(request: Request) -> Response:
    return _settings_response(request, warnings=(), error=None, message=None)


async def settings_save(request: Request) -> Response:
    form = await _form(request)
    result = await asyncio.to_thread(apply_form, form)
    if result.error:
        message = None
    elif result.changed:
        message = "Configuração gravada."
    else:
        message = "Nada mudou."
    return _settings_response(request, warnings=result.warnings, error=result.error, message=message)


async def history_page(request: Request) -> Response:
    rows = await asyncio.to_thread(_history_views)
    return page(
        request,
        "history.html",
        {"title": "Histórico", "active": "history", "rows": rows, "warning": None},
    )


async def history_undo(request: Request) -> Response:
    change_id = request.path_params["change_id"]
    if not isinstance(change_id, int):
        return _note(request, "Alteração inválida. Abra o histórico de novo.", status_code=400)
    warning, rows = await asyncio.to_thread(_undo, change_id)
    if _hx(request):
        return page(request, "history_list.html", {"rows": rows, "warning": warning})
    return page(
        request,
        "history.html",
        {"title": "Histórico", "active": "history", "rows": rows, "warning": warning},
    )


async def shutdown(request: Request) -> Response:
    state = web_state(request)
    if state.jobs.running():
        return _note(request, _SHUTDOWN_BUSY, status_code=409)
    background = BackgroundTask(_stop, state.server) if state.server is not None else None
    return page(
        request,
        "shutdown.html",
        {"title": "Encerrar", "active": ""},
        background=background,
    )


def _read_status(gate: RuntimeGate) -> tuple[str | None, IndexStatus | None, str]:
    if not gate.lock.acquire(blocking=False):
        return (
            "Há uma sincronização em andamento. Espere ela terminar e atualize a página.",
            None,
            _settings_path(gate),
        )
    try:
        notice = gate.host.before_call()
        try:
            status = gate.host.runtime.status()
        except NixError as exc:
            return _merge(notice, exc.message), None, _settings_path(gate)
        return notice, status, _settings_path(gate)
    finally:
        gate.lock.release()


def _sync_context(gate: RuntimeGate) -> tuple[str | None, str]:
    if not gate.lock.acquire(blocking=False):
        return (
            "Há uma sincronização em andamento. Espere ela terminar e atualize a página.",
            gate.host.runtime.config.index.embedding_model,
        )
    try:
        notice = gate.host.before_call()
        return notice, gate.host.runtime.config.index.embedding_model
    finally:
        gate.lock.release()


def _preview(gate: RuntimeGate) -> tuple[str | None, SyncReport | None, str | None]:
    if not gate.lock.acquire(blocking=False):
        return None, None, _BUSY
    try:
        notice = gate.host.before_call()
        try:
            report = gate.host.runtime.indexer.sync(dry_run=True, trigger="manual")
        except NixError as exc:
            return notice, None, exc.message
        return notice, report, None
    finally:
        gate.lock.release()


def _doctor_report(gate: RuntimeGate) -> DoctorReport:
    if not gate.lock.acquire(blocking=False):
        return build_doctor_report(
            inspect_index=False,
            index_problem="Há uma sincronização em andamento. Espere ela terminar e atualize o diagnóstico.",
        )
    try:
        notice = gate.host.before_call()
        try:
            status = gate.host.runtime.status()
        except NixError as exc:
            report = build_doctor_report(inspect_index=False, index_problem=exc.message)
        else:
            report = build_doctor_report(inspect_index=False, index_status=status)
        if notice:
            report.checks.insert(0, DoctorCheck("Processo", "warn", notice))
        return report
    finally:
        gate.lock.release()


def _settings_path(gate: RuntimeGate) -> str:
    path = gate.host.runtime.config.settings_path
    if path is None:
        return "—"
    return str(path)


def _merge(notice: str | None, message: str) -> str:
    if notice:
        return f"{notice} {message}"
    return message


def _settings_response(
    request: Request,
    *,
    warnings: tuple[str, ...],
    error: str | None,
    message: str | None,
) -> Response:
    return page(
        request,
        "settings.html",
        {
            "title": "Configuração",
            "active": "settings",
            "groups": field_groups(),
            "warnings": warnings,
            "error": error,
            "message": message,
        },
    )


def _history_views() -> list[HistoryView]:
    rows: list[HistoryView] = []
    for row in history(50):
        rows.append(
            HistoryView(
                id=row.id,
                changed_at=row.changed_at,
                source=row.source,
                dotted=row.dotted,
                old_value=_show(row.old_value),
                new_value=_show(row.new_value),
            )
        )
    return rows


def _undo(change_id: int) -> tuple[str | None, list[HistoryView]]:
    warning: str | None = None
    try:
        result = revert_change(change_id, source="ui")
    except NixError as exc:
        warning = exc.message
    else:
        warning = result.warning
    return warning, _history_views()


def _show(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


async def _form(request: Request) -> dict[str, str]:
    raw = await request.body()
    parsed = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _hx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def _note(request: Request, message: str, *, status_code: int) -> Response:
    context = {"message": message, "title": "Nix", "active": "sync"}
    if _hx(request):
        return page(request, "fragment_message.html", context, status_code=status_code)
    return page(request, "message.html", context, status_code=status_code)


def _stop(server: ServerControl) -> None:
    server.should_exit = True


def _progress_html(event: SyncProgress) -> str:
    return fragment(
        "sync_progress.html",
        current=event.current,
        total=event.total,
        maximum=event.total if event.total > 0 else 1,
        rel_path=event.rel_path,
        action=_ACTIONS.get(event.action, event.action),
        detail=event.detail,
    )


def _outcome_html(item: SyncReport | NixError) -> str:
    if isinstance(item, NixError):
        return fragment("sync_done.html", summary=None, errors=[], error=item.message, tokenizer=None)
    tokenizer = approximate_tokenizer_hint() if item.tokenizer_approximate else None
    return fragment(
        "sync_done.html",
        summary=item.summary_pt(),
        errors=item.errors,
        error=None,
        tokenizer=tokenizer,
    )


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
        "data": fragment(
            "sync_done.html",
            summary=None,
            errors=[],
            error="A sincronização terminou sem um resultado. Rode `nix sync` de novo.",
            tokenizer=None,
        ),
    }


async def _idle() -> AsyncIterator[dict[str, str]]:
    html = fragment(
        "sync_done.html",
        summary=None,
        errors=[],
        error="Nenhuma sincronização em andamento.",
        tokenizer=None,
    )
    yield {"event": "done", "data": html}
