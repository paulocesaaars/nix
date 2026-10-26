"""Manutenção: backups, configuração e histórico."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import FileResponse, Response

from nix.config.editor import history, revert_change
from nix.core.admin.backups import BackupDiff, BackupEntry, backup_file, diff_backup, list_backups, restore_backup
from nix.core.errors import NixError, VaultError
from nix.core.models import WriteResult
from nix.core.runtime import Runtime
from nix.web.render import page
from nix.web.routes.common import form_data, is_hx, query, run_gated
from nix.web.settings_form import apply_form, field_groups
from nix.web.state import web_state

_RESTORE_CONFIRM = 'Marque "Confirmo a restauração" para gravar o backup por cima da nota.'
_RESTORE_BUSY = "Há uma sincronização em andamento. Espere ela terminar e restaure de novo."


@dataclass(frozen=True)
class HistoryView:
    id: int
    changed_at: str
    source: str
    dotted: str
    old_value: str
    new_value: str


async def backups_page(request: Request) -> Response:
    config = web_state(request).gate.host.runtime.config
    try:
        entries: list[BackupEntry] = await asyncio.to_thread(list_backups, config)
        error = None
    except OSError as exc:
        entries, error = [], f"Não foi possível ler {config.safety.backup_path}: {exc}. Verifique safety.backup_dir."
    return page(
        request,
        "backups.html",
        {
            "title": "Backups",
            "active": "backups",
            "entries": entries,
            "error": error,
            "backup_dir": str(config.safety.backup_path),
            "retention": config.safety.backup_retention_days,
            "enabled": config.safety.backup_before_overwrite,
        },
    )


async def backup_view(request: Request) -> Response:
    stamp = query(request, "stamp")
    path = query(request, "path")
    config = web_state(request).gate.host.runtime.config
    diff: BackupDiff | None = None
    error: str | None = None
    try:
        diff = await asyncio.to_thread(diff_backup, config, stamp, path)
    except NixError as exc:
        error = exc.message
    return page(
        request,
        "backup.html",
        {"title": "Backup", "active": "backups", "stamp": stamp, "path": path, "diff": diff, "error": error},
    )


async def backup_download(request: Request) -> Response:
    stamp = query(request, "stamp")
    path = query(request, "path")
    config = web_state(request).gate.host.runtime.config
    try:
        source = await asyncio.to_thread(backup_file, config, stamp, path)
    except NixError as exc:
        return page(
            request,
            "message.html",
            {"title": "Backups", "active": "backups", "message": exc.message},
            status_code=404,
        )
    name = source.name if source.suffix else f"{source.name}.txt"
    return FileResponse(source, filename=f"{stamp}-{name}", headers={"Cache-Control": "no-store"})


async def backup_restore(request: Request) -> Response:
    form = await form_data(request)
    stamp = form.get("stamp", "")
    path = form.get("path", "")
    if form.get("confirm", "") != "on":
        return _restore_result(request, None, _RESTORE_CONFIRM)
    if web_state(request).jobs.running():
        return _restore_result(request, None, _RESTORE_BUSY)
    result = await run_gated(
        request, lambda runtime: _restore(runtime, stamp, path), busy=_RESTORE_BUSY
    )
    return _restore_result(request, result.value, result.error)


async def settings_page(request: Request) -> Response:
    return _settings_response(request, warnings=(), error=None, message=None)


async def settings_save(request: Request) -> Response:
    form = await form_data(request)
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
        {"title": "Histórico", "active": "history", "rows": rows, "warning": None, "message": None},
    )


async def history_undo(request: Request) -> Response:
    change_id = int(request.path_params["change_id"])
    warning, message, rows = await asyncio.to_thread(_undo, change_id)
    context = {"rows": rows, "warning": warning, "message": message}
    if is_hx(request):
        return page(request, "history_list.html", context)
    context.update(title="Histórico", active="history")
    return page(request, "history.html", context)


def _restore(runtime: Runtime, stamp: str, path: str) -> WriteResult:
    try:
        return restore_backup(runtime, stamp, path)
    except OSError as exc:
        raise VaultError(
            f"Não foi possível restaurar {path}: {exc}. "
            "Verifique permissões e espaço em disco; a nota atual não foi alterada se o erro veio antes da gravação."
        ) from exc


def _restore_result(request: Request, written: WriteResult | None, error: str | None) -> Response:
    context = {"written": written, "error": error}
    if is_hx(request):
        return page(request, "backup_restored.html", context)
    context.update(title="Backups", active="backups")
    return page(request, "backup_restored_page.html", context)


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
    return [
        HistoryView(
            id=row.id,
            changed_at=row.changed_at,
            source=row.source,
            dotted=row.dotted,
            old_value=_show(row.old_value),
            new_value=_show(row.new_value),
        )
        for row in history(50)
    ]


def _undo(change_id: int) -> tuple[str | None, str | None, list[HistoryView]]:
    try:
        result = revert_change(change_id, source="ui")
    except NixError as exc:
        return exc.message, None, _history_views()
    return result.warning, f"Alteração #{change_id} desfeita.", _history_views()


def _show(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
