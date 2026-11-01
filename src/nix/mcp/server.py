"""Servidor MCP via stdio."""

from __future__ import annotations

import base64
import contextlib
import sys
from importlib.resources import files
from typing import Any

from nix import __version__
from nix.config.loader import load_config, require_initialized
from nix.core.errors import ConfigError, NixError
from nix.core.runtime import RuntimeHost
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


# O initialize manda este PNG pequeno, derivado do nix.png fonte. O MCPB segue com o fonte.
_INITIALIZE_ICON = "nix-48.png"


def _server_icons() -> list[Any]:
    """PNG pequeno do pacote como data URI. O initialize publica isso em serverInfo.icons."""
    try:
        from mcp.types import Icon
    except ImportError as exc:
        raise ConfigError(
            "SDK MCP incompatível: o initialize não aceita ícones. "
            "Atualize com `pip install 'mcp>=1.9.0'`."
        ) from exc
    try:
        png = files("nix.mcp").joinpath(_INITIALIZE_ICON).read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(
            f"Não achei o ícone {_INITIALIZE_ICON} nos dados do pacote. Reinstale com `pip install .`."
        ) from exc
    if len(png) < 24 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ConfigError(
            f"O arquivo {_INITIALIZE_ICON} do pacote não é um PNG válido. Reinstale com `pip install .`."
        )
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    if width <= 0 or height <= 0:
        raise ConfigError(
            f"O arquivo {_INITIALIZE_ICON} do pacote não tem tamanho válido. Reinstale com `pip install .`."
        )
    encoded = base64.b64encode(png).decode("ascii")
    return [
        Icon(
            src=f"data:image/png;base64,{encoded}",
            mime_type="image/png",
            sizes=[f"{width}x{height}"],
        )
    ]


def build_server() -> Any:
    """Cria o servidor MCP. O initialize leva o ícone em serverInfo.icons.

    O SDK instalado (MCPServer, o FastMCP do mcp 2.x) recebe `icons` no construtor.
    As ferramentas não recebem ícone próprio.
    """
    cls = _server_class()
    icons = _server_icons()
    try:
        return cls("nix", version=__version__, log_level="ERROR", icons=icons)
    except TypeError:
        try:
            return cls("nix", log_level="ERROR", icons=icons)
        except TypeError as exc:
            raise ConfigError(
                "Não foi possível instanciar o servidor MCP. "
                "Atualize com `pip install 'mcp>=1.9.0'`."
            ) from exc


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
    require_initialized()
    config = load_config()
    host = RuntimeHost(config)
    log = get_logger("nix.mcp")
    server = build_server()
    register_tools(server, host)
    register_resources(server, host)
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
        host.close()
        log.info("Servidor MCP encerrado")
