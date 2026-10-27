"""Rotas da interface local."""

from __future__ import annotations

from pathlib import Path

from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from nix.web.routes import integration, maintenance, ops, sessions, vault


def build_routes() -> list[BaseRoute]:
    static = Path(__file__).parent.parent / "static"
    return [
        Route("/", ops.status_page, methods=["GET"]),
        Route("/sync", ops.sync_page, methods=["GET"]),
        Route("/sync/preview", ops.sync_preview, methods=["POST"]),
        Route("/sync/start", ops.sync_start, methods=["POST"]),
        Route("/sync/events", ops.sync_events, methods=["GET"]),
        Route("/doctor", ops.doctor_page, methods=["GET"]),
        Route("/search", vault.search_page, methods=["GET"]),
        Route("/notes", vault.notes_page, methods=["GET"]),
        Route("/notes/view", vault.note_view, methods=["GET"]),
        Route("/tags", vault.tags_page, methods=["GET"]),
        Route("/insights", vault.insights_page, methods=["GET"]),
        Route("/connect", integration.connect_page, methods=["GET"]),
        Route("/traffic", integration.traffic_page, methods=["GET"]),
        Route("/sessions", sessions.sessions_page, methods=["GET"]),
        Route("/sessions/handoff/cancel", sessions.handoff_cancel, methods=["POST"]),
        Route("/backups", maintenance.backups_page, methods=["GET"]),
        Route("/backups/view", maintenance.backup_view, methods=["GET"]),
        Route("/backups/download", maintenance.backup_download, methods=["GET"]),
        Route("/backups/restore", maintenance.backup_restore, methods=["POST"]),
        Route("/settings", maintenance.settings_page, methods=["GET"]),
        Route("/settings", maintenance.settings_save, methods=["POST"]),
        Route("/vaults", maintenance.vaults_page, methods=["GET"]),
        Route("/vaults/add", maintenance.vaults_add, methods=["POST"]),
        Route("/vaults/rename", maintenance.vaults_rename, methods=["POST"]),
        Route("/vaults/remove", maintenance.vaults_remove, methods=["POST"]),
        Route("/vaults/default", maintenance.vaults_default, methods=["POST"]),
        Route("/vaults/path", maintenance.vaults_path, methods=["POST"]),
        Route("/vaults/set", maintenance.vaults_set, methods=["POST"]),
        Route("/history", maintenance.history_page, methods=["GET"]),
        Route("/history/{change_id:int}/undo", maintenance.history_undo, methods=["POST"]),
        Route("/shutdown", ops.shutdown, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=static), name="static"),
    ]
