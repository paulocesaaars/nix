"""Recursos MCP: notas como nix://note/{+rel_path} (barras no caminho)."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from nix.core.errors import PathEscapeError
from nix.core.runtime import Runtime
from nix.core.vault.paths import assert_accessible
from nix.observability.logging import get_logger

logger = get_logger("nix.mcp.resources")


def register_resources(server: Any, runtime: Runtime) -> None:
    include = runtime.config.vault.include
    exclude = runtime.config.vault.exclude

    def _read_note(rel_path: str) -> str:
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
