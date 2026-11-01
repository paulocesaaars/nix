"""Rotas da interface local."""

from __future__ import annotations

from pathlib import Path

from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from nix.web.routes import brain, integration, maintenance, ops, wiki


def build_routes() -> list[BaseRoute]:
    static = Path(__file__).parent.parent / "static"
    return [
        Route("/", ops.status_page, methods=["GET"]),
        Route("/sync", ops.sync_page, methods=["GET"]),
        Route("/sync/preview", ops.sync_preview, methods=["POST"]),
        Route("/sync/start", ops.sync_start, methods=["POST"]),
        Route("/sync/events", ops.sync_events, methods=["GET"]),
        Route("/doctor", ops.doctor_page, methods=["GET"]),
        Route("/search", wiki.search_page, methods=["GET"]),
        Route("/notes", wiki.notes_page, methods=["GET"]),
        Route("/notes/view", wiki.note_view, methods=["GET"]),
        Route("/tags", wiki.tags_page, methods=["GET"]),
        Route("/insights", wiki.insights_page, methods=["GET"]),
        Route("/brain", brain.panel_page, methods=["GET"]),
        Route("/brain/inbox", brain.inbox_page, methods=["GET"]),
        Route("/brain/profile", brain.profile_page, methods=["GET"]),
        Route("/brain/project", brain.project_page, methods=["GET"]),
        Route("/connect", integration.connect_page, methods=["GET"]),
        Route("/traffic", integration.traffic_page, methods=["GET"]),
        Route("/backups", maintenance.backups_page, methods=["GET"]),
        Route("/backups/view", maintenance.backup_view, methods=["GET"]),
        Route("/backups/download", maintenance.backup_download, methods=["GET"]),
        Route("/backups/restore", maintenance.backup_restore, methods=["POST"]),
        Route("/settings", maintenance.settings_page, methods=["GET"]),
        Route("/settings", maintenance.settings_save, methods=["POST"]),
        Route("/wikis", maintenance.vaults_page, methods=["GET"]),
        Route("/wikis/add", maintenance.vaults_add, methods=["POST"]),
        Route("/wikis/rename", maintenance.vaults_rename, methods=["POST"]),
        Route("/wikis/remove", maintenance.vaults_remove, methods=["POST"]),
        Route("/wikis/default", maintenance.vaults_default, methods=["POST"]),
        Route("/wikis/path", maintenance.vaults_path, methods=["POST"]),
        Route("/wikis/set", maintenance.vaults_set, methods=["POST"]),
        Route("/history", maintenance.history_page, methods=["GET"]),
        Route("/history/{change_id:int}/undo", maintenance.history_undo, methods=["POST"]),
        Route("/shutdown", ops.shutdown, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=static), name="static"),
    ]
