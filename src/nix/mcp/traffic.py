"""Logs de tráfego MCP: quem chamou, qual ferramenta, duração."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from nix.observability.logging import get_logger

logger = get_logger("nix.mcp")

_QUIET_PREFIXES = ("notifications/", "ping")
_CONTENT_KEYS = frozenset({"content", "body", "text", "markdown", "html", "replacement"})
_MAX_VALUE = 80
_CallNext = Callable[[Any], Awaitable[Any]]


def install_traffic_logging(server: Any, *, log_prompts: bool = False) -> None:
    """Encaixa o middleware de tráfego, se o SDK expuser a cadeia."""
    chain = getattr(server, "middleware", None)
    if chain is None or not hasattr(chain, "append"):
        logger.warning(
            "SDK MCP sem middleware; interações não serão logadas no protocolo."
        )
        return
    chain.append(_make_traffic_logger(log_prompts))


def _is_quiet(method: str) -> bool:
    return method == "ping" or method.startswith(_QUIET_PREFIXES)


def _fmt_value(key: str, value: Any) -> str | None:
    if key == "confirm":
        return None
    if key in _CONTENT_KEYS:
        size = len(str(value)) if value is not None else 0
        return f"{key}=<{size} caracteres>"
    if value is None:
        return None
    if isinstance(value, str):
        text = " ".join(value.split())
        if len(text) > _MAX_VALUE:
            text = text[:_MAX_VALUE] + "…"
        return f"{key}={text!r}"
    if isinstance(value, bool):
        return f"{key}={str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"{key}={value}"
    if isinstance(value, list):
        return f"{key}=[{len(value)}]"
    return f"{key}=…"


def _fmt_args(args: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, value in args.items():
        formatted = _fmt_value(key, value)
        if formatted:
            parts.append(formatted)
    return " ".join(parts)


def describe_request(
    method: str,
    params: Mapping[str, Any] | None,
    *,
    log_prompts: bool = False,
) -> str:
    """Rótulo curto da mensagem MCP, sem o corpo das notas."""
    data = params or {}
    if method == "initialize":
        info = data.get("clientInfo")
        if isinstance(info, Mapping):
            name = str(info.get("name") or "cliente")
            version = str(info.get("version") or "").strip()
            return f"initialize {name} {version}".strip()
        return "initialize"
    if method == "tools/call":
        name = str(data.get("name") or "?")
        if not log_prompts:
            return f"tools/call {name}"
        raw_args = data.get("arguments")
        extra = _fmt_args(raw_args) if isinstance(raw_args, Mapping) else ""
        return f"tools/call {name} {extra}".strip()
    if method == "resources/read":
        uri = str(data.get("uri") or "")
        return f"resources/read {uri}".strip()
    return method


def _make_traffic_logger(log_prompts: bool) -> Any:
    async def log_mcp_traffic(ctx: Any, call_next: _CallNext) -> Any:
        method = str(getattr(ctx, "method", "") or "unknown")
        params = getattr(ctx, "params", None)
        payload = params if isinstance(params, Mapping) else None
        label = describe_request(method, payload, log_prompts=log_prompts)
        level = logging.DEBUG if _is_quiet(method) else logging.INFO
        logger.log(level, "→ %s", label)
        started = time.perf_counter()
        try:
            result = await call_next(ctx)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.error("← %s erro (%.0f ms): %s", label, elapsed_ms, exc)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        failed = bool(getattr(result, "isError", False))
        if failed:
            logger.warning("← %s falhou (%.0f ms)", label, elapsed_ms)
        else:
            logger.log(level, "← %s ok (%.0f ms)", label, elapsed_ms)
        return result

    return log_mcp_traffic
