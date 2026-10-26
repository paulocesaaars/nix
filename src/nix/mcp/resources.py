"""Recursos MCP: notas como nix://note/{+rel_path} (barras no caminho)."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from nix.core.errors import PathEscapeError
from nix.core.runtime import RuntimeHost
from nix.core.vault.paths import assert_accessible
from nix.observability.logging import get_logger

logger = get_logger("nix.mcp.resources")


def register_resources(server: Any, host: RuntimeHost) -> None:
    logged_warning: str | None = None

    def _read_note(rel_path: str) -> str:
        nonlocal logged_warning
        warning = host.before_call()
        if warning != logged_warning:
            logged_warning = warning
            if warning:
                logger.warning("%s", warning)
        runtime = host.runtime
        include = runtime.config.vault.include
        exclude = runtime.config.vault.exclude
        posix = unquote(rel_path).replace("|", "/")
        try:
            posix = assert_accessible(posix, include, exclude)
        except PathEscapeError:
            logger.warning("Recurso bloqueado por filtro: %s", posix)
            raise
        try:
            return runtime.reader.read_text(posix)
        except Exception:
            logger.warning("Falha ao ler recurso %s", posix, exc_info=True)
            raise

    @server.resource("nix://note/{+rel_path}")  # type: ignore[untyped-decorator]
    def note_resource(rel_path: str) -> str:
        return _read_note(rel_path)
