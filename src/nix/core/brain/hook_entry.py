"""Ponto de entrada de `nix-hook brain --event E --agent A`.

Só a biblioteca padrão e os módulos leves de `core/brain`. O código de saída é
sempre 0: um erro do hook não pode derrubar o agente.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nix.config.paths import default_state_dir
from nix.core.brain.agents import AGENTS
from nix.core.brain.capture import record
from nix.core.brain.events import EVENT_TYPES, normalize
from nix.core.brain.limits import load_limits

_MAX_STDIN = 4 * 1024 * 1024


def main(argv: list[str]) -> int:
    """`argv` sem o nome do programa nem a palavra `brain`. Devolve sempre 0."""
    try:
        _run(argv)
    except BaseException:  # noqa: BLE001 - o hook nunca falha para o agente
        _log_error()
    return 0


def _run(argv: list[str]) -> None:
    event_type, agent = _parse(argv)
    payload = _read_payload()
    event = normalize(agent, event_type, payload, load_limits())
    accepted = record(event)
    if accepted:
        from nix.core.brain.tokens import observe

        observe(event, payload)
    if event.type == "session-start" and accepted:
        _print_briefing(event.agent, event.project, event.storage_key)
    if event.type == "session-end" and accepted:
        from nix.core.brain.worker import schedule

        schedule(event.storage_key)


def _parse(argv: list[str]) -> tuple[str, str]:
    event_type = "other"
    agent = ""
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--event", "-e"} and index + 1 < len(argv):
            event_type = argv[index + 1]
            index += 2
        elif arg.startswith("--event="):
            event_type = arg.split("=", 1)[1]
            index += 1
        elif arg in {"--agent", "-a"} and index + 1 < len(argv):
            agent = argv[index + 1]
            index += 2
        elif arg.startswith("--agent="):
            agent = arg.split("=", 1)[1]
            index += 1
        else:
            index += 1
    if event_type not in EVENT_TYPES:
        event_type = "other"
    if agent not in AGENTS:
        raise ValueError(f"agente {agent!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    return event_type, agent


def _read_payload() -> dict[str, Any]:
    stream = sys.stdin
    if stream is None or stream.isatty():
        return {}
    buffer = getattr(stream, "buffer", None)
    raw = buffer.read(_MAX_STDIN + 1) if buffer is not None else stream.read(_MAX_STDIN + 1)
    if len(raw) > _MAX_STDIN:
        return {}
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {"prompt": text}
    return data if isinstance(data, dict) else {"prompt": text}


def _print_briefing(agent: str, project: str, session_key: str) -> None:
    """O início da sessão mostra o briefing e não consome o handoff."""
    from nix.core.brain.agents import context_output
    from nix.core.brain.briefing import build_briefing

    text = build_briefing(project, current_session=session_key, agent=agent)
    rendered = context_output(agent, text) if text else ""
    if not rendered:
        return
    sys.stdout.write(rendered + "\n")
    sys.stdout.flush()


def _log_error() -> None:
    try:
        directory = default_state_dir() / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with Path(directory / "brain-hook.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {traceback.format_exc()}\n")
    except BaseException:  # noqa: BLE001
        return
