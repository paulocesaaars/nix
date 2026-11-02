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

from nix.config.editor import mark_editor_called
from nix.config.embedding_present import sync_model_hint
from nix.config.loader import load_config
from nix.core.admin.doctor import DoctorCheck, DoctorReport, build_doctor_report
from nix.core.admin.traffic import TrafficCall, TrafficStore
from nix.core.errors import ConfigError, NixError
from nix.core.index.lock import mark_sync_job, unmark_sync_job
from nix.core.index.sync import combine_sync_reports
from nix.core.index.tokenize import approximate_tokenizer_hint
from nix.core.models import IndexStatus, SyncProgress, SyncReport
from nix.core.runtime import Runtime, WikiSpec
from nix.observability.logging import get_logger
from nix.web.jobs import RuntimeGate, SyncJobs, SyncRun, launch_sync, vault_busy_message
from nix.web.render import fragment, page
from nix.web.routes.common import BUSY, Gated, form_data, is_hx, note, run_gated
from nix.web.state import ServerControl, WebState, web_state

logger = get_logger("nix.web")

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
    wiki_name: str


@dataclass(frozen=True)
class StartStep:
    title: str
    done: bool
    detail: str
    href: str


@dataclass(frozen=True)
class StartChecklist:
    """Caminho inicial. Some quando a wiki selecionada já sincronizou e a busca foi pedida."""

    intro: str | None
    steps: tuple[StartStep, ...]


@dataclass(frozen=True)
class SyncContext:
    model: str
    runs: list[SyncRunView]


async def status_page(request: Request) -> Response:
    result = await run_gated(request, _overview)
    calls, traffic_ok = await asyncio.to_thread(_recent_calls)
    overview = result.value
    checklist = await asyncio.to_thread(_start_checklist, overview, calls, traffic_ok)
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
            "checklist": checklist,
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
    selected = form.get("wiki") or ""
    all_wikis = form.get("all_wikis") == "on"
    if state.jobs.running():
        return _sync_conflict(request, state, _PREVIEW_WAIT, selected=selected, all_wikis=all_wikis)
    spec = _sync_spec(selected or None, all_wikis)
    result = await asyncio.to_thread(partial(_preview_many, state.gate, spec, state.jobs))
    if state.jobs.running():
        return _sync_conflict(request, state, _PREVIEW_WAIT, selected=selected, all_wikis=all_wikis)
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
    all_wikis = form.get("all_wikis") == "on"
    selected = form.get("wiki") or ""
    if full and form.get("confirm_full", "") != "on":
        return note(request, _FULL, status_code=200, active="sync")
    run = state.jobs.begin(asyncio.get_running_loop())
    if run is None:
        return _sync_conflict(request, state, BUSY, selected=selected, all_wikis=all_wikis)
    run.selected_wiki = selected
    run.all_wikis = all_wikis
    spec = _sync_spec(selected or None, all_wikis)
    _called, notice = await asyncio.to_thread(state.gate.try_before_call)
    model = state.gate.host.config.index.embedding_model
    launch_sync(state.jobs, state.gate, run, full=full, spec=spec)
    if is_hx(request):
        # O POST termina quando a thread começa. O fieldset segue desligado até o fim do SSE.
        body = fragment("sync_live.html", notice=notice, full=full)
        body += _controls_oob(state, model, running=True, selected_wiki=selected, all_wikis=all_wikis)
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
            "selected_wiki": selected,
            "all_wikis": all_wikis,
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
    return Overview(status=runtime.status(), runs=_runs(runtime, 3), wiki_name=runtime.wiki.name)


def _start_checklist(
    overview: Overview | None,
    calls: list[TrafficCall],
    traffic_ok: bool,
) -> StartChecklist | None:
    """Monta o bloco só com o índice lido e enquanto faltar sync ou busca pedida.

    Linha em `mcp_calls` com a marca apagada grava a marca uma vez. Falha de leitura
    do tráfego não derruba a página: a busca fica pendente só se a marca também for falsa.
    """
    try:
        config = load_config()
    except (ConfigError, NixError) as exc:
        logger.warning(
            "Não foi possível ler a configuração para o caminho inicial: %s. Atualize a página de Status.",
            exc,
        )
        return None
    called = config.ui.editor_called
    has_calls = traffic_ok and bool(calls)
    if has_calls and not called:
        try:
            mark_editor_called(source="ui")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Não foi possível gravar que o editor chamou uma ferramenta: %s. "
                "A página de Status segue; a próxima visita tenta de novo.",
                exc,
            )
        else:
            called = True
    if overview is None:
        return None
    search_done = called or has_calls
    synced = bool(overview.status.last_sync_at)
    if synced and search_done:
        return None
    selected = overview.wiki_name
    default = config.default_wiki.name
    intro = None
    if selected.casefold() != default.casefold():
        intro = f"Você está em {selected}. A padrão é {default}."
    sync_detail = (
        f"A wiki {selected} já foi sincronizada."
        if synced
        else f"A wiki {selected} ainda não foi sincronizada."
    )
    search_detail = (
        "O editor já pediu uma busca." if search_done else "Abra o editor e peça para buscar uma nota."
    )
    return StartChecklist(
        intro=intro,
        steps=(
            StartStep("Wiki cadastrada", True, f"A wiki padrão é {default}.", "/wikis"),
            StartStep("Sincronizar o índice", synced, sync_detail, "/sync"),
            StartStep("Pedir uma busca ao editor", search_done, search_detail, "/connect"),
        ),
    )


def _sync_context(runtime: Runtime) -> SyncContext:
    return SyncContext(model=runtime.config.index.embedding_model, runs=_runs(runtime, 5))


def _preview_many(gate: RuntimeGate, spec: WikiSpec, jobs: SyncJobs) -> Gated[SyncReport]:
    """Dry-run de uma wiki por vez. A trava de cada um solta antes do próximo."""
    if jobs.running():
        return Gated(None, None, _PREVIEW_WAIT)
    notice = gate.before_call()
    try:
        selected = gate.host.vaults_for(spec)
    except NixError as exc:
        return Gated(None, notice, exc.message)
    reports: list[tuple[str, SyncReport]] = []
    for wiki in selected:
        if jobs.running():
            return Gated(None, notice, _PREVIEW_WAIT)
        lock = gate.lock_for(wiki.name)
        if not lock.acquire(blocking=False):
            reports.append((wiki.name, SyncReport(failed=1, errors=[vault_busy_message(wiki.name)])))
            continue
        try:
            mark_sync_job(wiki.name)
            if jobs.running():
                return Gated(None, notice, _PREVIEW_WAIT)
            try:
                runtime = gate.host.resolve(wiki.name)
                report = runtime.indexer.sync(dry_run=True, trigger="manual")
            except NixError as exc:
                report = SyncReport(failed=1, errors=[exc.message])
            reports.append((wiki.name, report))
        finally:
            unmark_sync_job(wiki.name)
            lock.release()
    if not reports:
        return Gated(None, notice, "Nenhuma wiki disponível para a prévia. Rode `nix wiki list`.")
    return Gated(combine_sync_reports(reports), notice, None)


def _sync_conflict(
    request: Request,
    state: WebState,
    message: str,
    *,
    selected: str,
    all_wikis: bool,
) -> Response:
    """Aviso de job em andamento. Não substitui o progresso nem varre a wiki."""
    if not is_hx(request):
        return note(request, message, status_code=409, active="sync")
    model = state.gate.host.config.index.embedding_model
    body = fragment("fragment_message.html", message=message)
    body += _controls_oob(
        state,
        model,
        running=True,
        selected_wiki=selected,
        all_wikis=all_wikis,
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


def _recent_calls() -> tuple[list[TrafficCall], bool]:
    """Chamadas recentes e se a leitura deu certo.

    Sem o arquivo ou com falha, a página segue. A falha deixa a busca do caminho
    inicial pendente só quando a marca `ui.editor_called` também é falsa.
    """
    try:
        return TrafficStore().recent(6), True
    except (sqlite3.Error, OSError):
        return [], False


def _doctor_report(gate: RuntimeGate) -> tuple[DoctorReport, str | None]:
    with gate.borrow("*") as borrowed:
        statuses: list[tuple[str, IndexStatus | None, str | None]] = []
        for runtime in borrowed.runtimes:
            try:
                statuses.append((runtime.wiki.name, runtime.status(), None))
            except NixError as exc:
                statuses.append((runtime.wiki.name, None, exc.message))
        for skip in borrowed.skipped:
            statuses.append((skip["wiki"], None, skip["message"]))
        report = build_doctor_report(
            inspect_index=False,
            wiki_statuses=statuses,
            index_problem=borrowed.error,
        )
        return report, borrowed.notice


def _sync_spec(wiki: str | None, all_wikis: bool) -> WikiSpec:
    if all_wikis:
        return "*"
    if wiki and wiki.strip():
        return wiki.strip()
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
        wiki=event.wiki,
    )


def _controls_oob(
    state: WebState,
    model: str,
    *,
    running: bool,
    selected_wiki: str = "",
    all_wikis: bool = False,
) -> str:
    """`#sync-controls` para o HTMX trocar fora de banda, igual ao da página."""
    return fragment(
        "sync_controls.html",
        running=running,
        oob=True,
        csrf_token=state.token,
        model=model,
        selected_wiki=selected_wiki,
        all_wikis=all_wikis,
    )


def _done_html(
    *,
    csrf_token: str,
    model: str,
    report: SyncReport | None = None,
    error: str | None = None,
    selected_wiki: str = "",
    all_wikis: bool = False,
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
        selected_wiki=selected_wiki,
        all_wikis=all_wikis,
    )


def _outcome_html(
    item: SyncReport | NixError,
    *,
    csrf_token: str,
    model: str,
    selected_wiki: str,
    all_wikis: bool,
) -> str:
    if isinstance(item, NixError):
        return _done_html(
            csrf_token=csrf_token,
            model=model,
            error=item.message,
            selected_wiki=selected_wiki,
            all_wikis=all_wikis,
        )
    return _done_html(
        csrf_token=csrf_token,
        model=model,
        report=item,
        selected_wiki=selected_wiki,
        all_wikis=all_wikis,
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
            selected_wiki=run.selected_wiki,
            all_wikis=run.all_wikis,
        )
        # sse-swap só troca o evento progress; done fecha a conexão e leva o mesmo resumo.
        yield {"event": "progress", "data": html}
        yield {"event": "done", "data": html}
        return
    html = _done_html(
        csrf_token=csrf_token,
        model=model,
        error="A sincronização terminou sem um resultado. Rode `nix sync` de novo.",
        selected_wiki=run.selected_wiki,
        all_wikis=run.all_wikis,
    )
    yield {"event": "progress", "data": html}
    yield {"event": "done", "data": html}


async def _idle(csrf_token: str, model: str) -> AsyncIterator[dict[str, str]]:
    html = _done_html(csrf_token=csrf_token, model=model, error="Nenhuma sincronização em andamento.")
    yield {"event": "progress", "data": html}
    yield {"event": "done", "data": html}
