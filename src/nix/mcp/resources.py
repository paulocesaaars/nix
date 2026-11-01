"""Recursos MCP: nota na wiki padrão ou numa wiki nomeada.

`nix://vault/...` continua aceito por uma versão e registra o aviso para usar `nix://wiki/`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from nix.core.errors import PathEscapeError
from nix.core.runtime import RuntimeHost
from nix.core.wiki.paths import assert_accessible
from nix.observability.logging import get_logger

logger = get_logger("nix.mcp.resources")


def register_resources(server: Any, host: RuntimeHost) -> None:
    logged_warning: str | None = None

    def _read_note(wiki_name: str | None, rel_path: str) -> str:
        nonlocal logged_warning
        warning = host.before_call()
        if warning != logged_warning:
            logged_warning = warning
            if warning:
                logger.warning("%s", warning)
        runtime = host.resolve(wiki_name)
        include = runtime.wiki.include
        exclude = runtime.wiki.exclude
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
        """Nota na wiki padrão. O caminho pode ter barras."""
        return _read_note(None, rel_path)

    @server.resource("nix://wiki/{name}/note/{+rel_path}")  # type: ignore[untyped-decorator]
    def wiki_note_resource(name: str, rel_path: str) -> str:
        """Nota numa wiki nomeada. Nome desconhecido lista as wikis e o padrão."""
        return _read_note(unquote(name), rel_path)

    @server.resource("nix://vault/{name}/note/{+rel_path}")  # type: ignore[untyped-decorator]
    def legacy_vault_note_resource(name: str, rel_path: str) -> str:
        """Obsoleto. Use nix://wiki/{name}/note/.... Devolve a mesma nota e avisa no log."""
        logger.warning("O recurso nix://vault/ está obsoleto. Use nix://wiki/.")
        return _read_note(unquote(name), rel_path)
