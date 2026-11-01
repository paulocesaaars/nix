"""Uso de tokens lido nos eventos, sem modelo de linguagem.

O mesmo id de resposta conta uma vez. Agente sem número fica como desconhecido.
"""

from __future__ import annotations

from typing import Any

from nix.core.brain.events import SessionEvent
from nix.core.brain.store import BrainStore

_ID_KEYS = ("response_id", "responseId", "message_id", "messageId")
_USAGE_KEYS = ("usage", "token_usage", "tokenUsage")
_INPUT_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens")
_OUTPUT_KEYS = ("output_tokens", "outputTokens", "completion_tokens", "completionTokens")


def observe(event: SessionEvent, payload: dict[str, Any], store: BrainStore | None = None) -> bool:
    """Grava o uso de um `stop` ou `post-tool`. Repetir o id não soma de novo."""
    if event.type not in {"stop", "post-tool"}:
        return False
    response_id = _response_id(payload)
    usage = _usage(payload)
    if not response_id or usage is None:
        return False
    incoming, outgoing, model = usage
    return (store or BrainStore()).record_tokens(
        response_id=response_id,
        session_key=event.storage_key,
        project_key=event.project,
        agent=event.agent,
        model=model,
        input_tokens=incoming,
        output_tokens=outgoing,
    )


def report(session_key: str, store: BrainStore | None = None) -> str:
    """Texto do uso da sessão. Sem números, a resposta é `desconhecido`."""
    lines = (store or BrainStore()).token_lines(session_key)
    if not lines:
        return "desconhecido"
    return "; ".join(lines)


def _response_id(payload: dict[str, Any]) -> str:
    for key in _ID_KEYS:
        found = _text(payload.get(key))
        if found:
            return found
    usage = _usage_dict(payload)
    if usage is None:
        return ""
    for key in ("response_id", "responseId", "id"):
        found = _text(usage.get(key))
        if found:
            return found
    return ""


def _usage(payload: dict[str, Any]) -> tuple[int, int, str] | None:
    usage = _usage_dict(payload)
    if usage is None:
        return None
    incoming = _number(usage, _INPUT_KEYS)
    outgoing = _number(usage, _OUTPUT_KEYS)
    if incoming is None and outgoing is None:
        return None
    model = _text(usage.get("model")) or _text(payload.get("model"))
    return incoming or 0, outgoing or 0, model


def _usage_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in _USAGE_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(data: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None
