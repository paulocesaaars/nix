"""Normalização dos eventos dos hooks para o formato único da Nix (RF-80 a RF-85).

Cada agente envia um JSON diferente no stdin. O comando do hook já diz o tipo
normalizado (`--event user-prompt`), então aqui só se extrai, com tolerância,
sessão, pasta, pedido e ferramenta.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nix.core.sessions.limits import HookLimits
from nix.core.sessions.sanitize import Sanitizer, truncate_utf8

EVENT_TYPES: tuple[str, ...] = (
    "session-start",
    "user-prompt",
    "pre-tool",
    "post-tool",
    "compact",
    "stop",
    "session-end",
    "other",
)

_EDIT_TOOL_HINTS = ("edit", "write", "patch", "replace", "create", "delete", "notebook", "rename", "move")
# `conversation_id` vem antes de `session_id`: no Cursor todo evento o traz, e o `sessionStart` repete o id.
_SESSION_KEYS = (
    "conversation_id",
    "conversationId",
    "trajectory_id",
    "session_id",
    "sessionId",
    "thread_id",
    "chat_id",
)
_CWD_KEYS = ("cwd", "workingDirectory", "working_directory", "workspace", "project_dir")
_PROMPT_KEYS = ("prompt", "user_prompt", "userPrompt", "message", "text", "input")
_TOOL_KEYS = ("tool_name", "toolName", "tool", "name")
_TOOL_INPUT_KEYS = ("tool_input", "toolInput", "toolArgs", "tool_args", "arguments", "args", "input", "parameters")
_TOOL_OUTPUT_KEYS = (
    "tool_response",
    "toolResponse",
    "tool_output",
    "toolOutput",
    "toolResult",
    "output",
    "result",
    "response",
)
_TARGET_KEYS = ("file_path", "filePath", "path", "target_file", "notebook_path", "file", "filename")
_COMMAND_KEYS = ("command", "cmd", "query", "pattern", "url", "description")
_SUMMARY_KEYS = ("summary", "compact_summary", "custom_instructions", "trigger", "reason")
_TS_KEYS = ("timestamp", "ts", "time", "created_at")


@dataclass(frozen=True)
class SessionEvent:
    id: str
    agent: str
    session_id: str
    project: str
    project_name: str
    cwd: str
    type: str
    ts: str
    tool: str
    target: str
    text: str
    is_error: bool

    @property
    def session_key(self) -> str:
        return f"{self.agent}:{self.session_id}"


def find_project(cwd: str) -> tuple[str, str]:
    """Raiz Git da pasta de trabalho ou a própria pasta. Devolve (chave, nome)."""
    start = Path(cwd) if cwd else Path.cwd()
    with contextlib.suppress(OSError):
        start = start.resolve()
    found = start
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            found = parent
            break
    key = found.as_posix()
    return key, found.name or key


def project_key_of(path: str) -> str:
    """Mesma chave de `find_project`, para quem já tem a raiz do projeto."""
    return find_project(path)[0]


def normalize(
    agent: str,
    event_type: str,
    payload: dict[str, Any],
    limits: HookLimits,
    *,
    now: datetime | None = None,
) -> SessionEvent:
    kind = event_type if event_type in EVENT_TYPES else "other"
    payload = _flatten_devin_desktop(payload)
    sanitizer = Sanitizer(limits.extra_redact_patterns)
    received = now or datetime.now(UTC)
    ts = _timestamp(payload, received)
    cwd = _cwd(payload)
    project, project_name = find_project(cwd)
    session_id = _session_id(payload, agent, project, ts)

    tool = ""
    target = ""
    text = ""
    is_error = False
    if kind == "user-prompt":
        text = _clip(sanitizer, _first_text(payload, _PROMPT_KEYS), limits.max_prompt_bytes)
    elif kind == "compact":
        text = _clip(sanitizer, _first_text(payload, _SUMMARY_KEYS), limits.max_prompt_bytes)
    elif kind in {"pre-tool", "post-tool"}:
        tool = str(_first(payload, _TOOL_KEYS) or "").strip()
        tool_input = _first(payload, _TOOL_INPUT_KEYS)
        target = _clip(sanitizer, _target_of(tool_input), limits.max_tool_bytes)
        if kind == "post-tool":
            output = _first(payload, _TOOL_OUTPUT_KEYS)
            is_error = _failed(payload, output)
            if is_error:
                text = _clip(sanitizer, _output_text(output, payload), limits.max_tool_bytes)

    event_id = _event_id(agent, session_id, kind, tool, target, text, ts)
    return SessionEvent(
        id=event_id,
        agent=agent,
        session_id=session_id,
        project=project,
        project_name=project_name,
        cwd=cwd,
        type=kind,
        ts=ts,
        tool=tool,
        target=target,
        text=text,
        is_error=is_error,
    )


def _flatten_devin_desktop(payload: dict[str, Any]) -> dict[str, Any]:
    """Devin Desktop manda `agent_action_name` e `tool_info`. Traduz para os campos comuns."""
    action = payload.get("agent_action_name")
    info = payload.get("tool_info")
    if not isinstance(action, str) or not isinstance(info, dict):
        return payload
    flat = dict(payload)
    if info.get("user_prompt"):
        flat["prompt"] = info["user_prompt"]
    if info.get("cwd"):
        flat["cwd"] = info["cwd"]
    if "run_command" in action:
        flat["tool_name"] = "run_command"
        flat["tool_input"] = {"command": info.get("command_line", "")}
    elif "write_code" in action:
        flat["tool_name"] = "write_code"
        flat["tool_input"] = {"file_path": info.get("file_path", "")}
    elif "read_code" in action:
        flat["tool_name"] = "read_code"
        flat["tool_input"] = {"file_path": info.get("file_path", "")}
    elif "mcp_tool_use" in action:
        flat["tool_name"] = f"mcp:{info.get('mcp_server_name', '')}/{info.get('mcp_tool_name', '')}"
        flat["tool_input"] = info.get("mcp_tool_arguments") or {}
    return flat


def is_edit_tool(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _EDIT_TOOL_HINTS)


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    value = _first(payload, keys)
    return _stringify(value)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_stringify(item.get("text") if isinstance(item, dict) else item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            if key in value:
                return _stringify(value[key])
    return str(value)


def _cwd(payload: dict[str, Any]) -> str:
    direct = _first(payload, _CWD_KEYS)
    if isinstance(direct, str) and direct:
        return direct
    roots = payload.get("workspace_roots") or payload.get("workspaceRoots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str):
        return roots[0]
    for name in ("CLAUDE_PROJECT_DIR", "DEVIN_PROJECT_DIR"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return os.getcwd()


def _timestamp(payload: dict[str, Any], received: datetime) -> str:
    raw = _first(payload, _TS_KEYS)
    if isinstance(raw, int | float) and raw > 0:
        seconds = raw / 1000 if raw > 1e11 else float(raw)
        try:
            return datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = received
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat(timespec="seconds")
    return received.astimezone(UTC).isoformat(timespec="seconds")


def _session_id(payload: dict[str, Any], agent: str, project: str, ts: str) -> str:
    raw = _first(payload, _SESSION_KEYS)
    if isinstance(raw, str | int) and str(raw).strip():
        return str(raw).strip()
    # Sem id do agente: uma sessão por agente, projeto e dia.
    digest = hashlib.sha256(f"{agent}|{project}|{ts[:10]}".encode()).hexdigest()
    return f"dia-{digest[:12]}"


def _target_of(tool_input: Any) -> str:
    if isinstance(tool_input, str):
        stripped = tool_input.strip()
        if stripped.startswith("{"):  # Copilot manda `toolArgs` como JSON em texto
            with contextlib.suppress(ValueError):
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return _target_of(parsed)
        return tool_input
    if not isinstance(tool_input, dict):
        return ""
    for key in _TARGET_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    for key in _COMMAND_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _failed(payload: dict[str, Any], output: Any) -> bool:
    for key in ("is_error", "isError", "error", "error_message"):
        if payload.get(key):
            return True
    if payload.get("success") is False:
        return True
    for key in ("exit_code", "exitCode", "status_code"):
        code = payload.get(key)
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return True
    if isinstance(output, dict):
        result_type = output.get("resultType")
        if isinstance(result_type, str) and result_type.lower() not in {"success", "ok"}:
            return True
        if output.get("is_error") or output.get("isError") or output.get("error") or output.get("interrupted"):
            return True
        if output.get("success") is False:
            return True
        code = output.get("exit_code", output.get("exitCode"))
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return True
    return False


def _output_text(output: Any, payload: dict[str, Any]) -> str:
    for key in ("error", "error_message"):
        error = payload.get(key)
        if isinstance(error, str) and error:
            return error
    if isinstance(output, dict):
        for key in ("error", "stderr", "message", "textResultForLlm", "stdout", "content"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return _stringify(output)


def _clip(sanitizer: Sanitizer, text: str, limit: int) -> str:
    # Corta antes de sanitizar para não varrer megabytes, e de novo depois do `[segredo removido]`.
    return truncate_utf8(sanitizer.clean(truncate_utf8(text, limit * 2)), limit)


def _event_id(agent: str, session_id: str, kind: str, tool: str, target: str, text: str, ts: str) -> str:
    """Determinístico: o mesmo evento recebido duas vezes no mesmo segundo não duplica (RF-82)."""
    material = "\x1f".join((agent, session_id, kind, tool, target, text[:512], ts))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
