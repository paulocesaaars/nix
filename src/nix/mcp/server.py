"""Servidor MCP via stdio."""

from __future__ import annotations

import contextlib
import sys
from typing import Any

from nix import __version__
from nix.config.loader import load_config
from nix.core.errors import ConfigError, NixError
from nix.core.runtime import Runtime
from nix.core.tools.registry import register_tools
from nix.mcp.resources import register_resources
from nix.mcp.traffic import install_traffic_logging
from nix.observability.logging import get_logger
from nix.observability.stdio import silence_progress_env


def _server_class() -> Any:
    """Prefere FastMCP; no SDK recente a classe pública é MCPServer."""
    candidates: list[Any] = []
    try:
        from mcp.server.fastmcp import FastMCP

        candidates.append(FastMCP)
    except ImportError:
        pass
    try:
        from mcp.server import FastMCP as FastMCPAlt

        candidates.append(FastMCPAlt)
    except ImportError:
        pass
    try:
        from mcp.server import MCPServer

        candidates.append(MCPServer)
    except ImportError:
        pass
    for cls in candidates:
        if callable(getattr(cls, "tool", None)) and callable(getattr(cls, "run", None)):
            return cls
    raise ConfigError(
        "SDK MCP incompatível: não há FastMCP/MCPServer com .tool() e .run(). "
        "Atualize com `pip install 'mcp>=1.9.0'`."
    )


def _emit_error(message: str) -> None:
    """Erro no stderr — stdout é do protocolo MCP."""
    sys.stderr.write(f"Erro: {message}\n")
    sys.stderr.flush()


def run_server() -> None:
    silence_progress_env()
    try:
        _serve()
    except NixError as exc:
        with contextlib.suppress(Exception):
            get_logger("nix.mcp").error("%s", exc.message)
        _emit_error(exc.message)
        raise SystemExit(1) from None


def _serve() -> None:
    config = load_config()
    runtime = Runtime.from_config(config)
    log = get_logger("nix.mcp")
    cls = _server_class()
    try:
        server = cls("nix", version=__version__, log_level="ERROR")
    except TypeError:
        try:
            server = cls("nix", log_level="ERROR")
        except TypeError as exc:
            raise ConfigError(
                "Não foi possível instanciar o servidor MCP. "
                "Atualize com `pip install 'mcp>=1.9.0'`."
            ) from exc
    register_tools(server, runtime)
    register_resources(server, runtime)
    install_traffic_logging(server, log_prompts=config.logging.log_prompts)
    try:
        log.info("Servidor MCP Nix iniciado (stdio)")
        try:
            server.run(transport="stdio")
        except TypeError as exc:
            raise ConfigError(
                "Este SDK MCP não aceita transport='stdio'. "
                "Atualize com `pip install 'mcp>=1.9.0'`."
            ) from exc
    finally:
        runtime.close()
        log.info("Servidor MCP encerrado")
