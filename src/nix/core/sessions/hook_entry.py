"""Ponto de entrada do `nix hook --event E --agent A` (RF-130 a RF-134).

Só a biblioteca padrão e os módulos leves de `core/sessions` são importados:
nada de Typer, CLI, Pydantic, índice ou Chroma. O código de saída é sempre 0 e
o erro vai para `.nix/logs/hook.log`, para o hook nunca atrapalhar o agente.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nix.config.paths import default_state_dir
from nix.core.sessions import drain
from nix.core.sessions.agents import AGENTS
from nix.core.sessions.events import EVENT_TYPES, normalize
from nix.core.sessions.handoff import create_for_session, format_output
from nix.core.sessions.limits import load_limits
from nix.core.sessions.store import SessionStore

_MAX_STDIN = 4 * 1024 * 1024


def main(argv: list[str]) -> int:
    """`argv` sem o nome do programa nem a palavra `hook`. Devolve sempre 0."""
    try:
        _run(argv)
    except BaseException:  # noqa: BLE001 - o hook nunca falha para o agente
        _log_error()
    return 0


def _run(argv: list[str]) -> None:
    event_type, agent = _parse(argv)
    payload = _read_payload()
    limits = load_limits()
    event = normalize(agent, event_type, payload, limits)
    store = SessionStore()
    if not store.has_hooks(event.project, agent):
        return
    inserted = store.record(event)
    if event.type == "session-start":
        _print_pending_handoff(store, agent, event.project, event.session_key)
    elif event.type == "session-end" and inserted:
        # Um `session-end` repetido não cria outro handoff nem dispara outro consolidador.
        _close_session(store, event.session_key, limits.folder)


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
        # Truncado, o JSON ficaria inválido e o pedaço viraria "prompt": o evento segue sem texto.
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


def _print_pending_handoff(store: SessionStore, agent: str, project: str, session_key: str) -> None:
    """O handoff pendente sai no stdout do `session-start` e é entregue uma só vez (RF-113)."""
    handoff = store.consume_handoff(project, f"hook:{agent}", not_from=session_key)
    if handoff is None:
        return
    output = format_output(agent, handoff.text)
    if output:
        sys.stdout.write(output + "\n")
        sys.stdout.flush()


def _close_session(store: SessionStore, session_key: str, folder: str) -> None:
    """`session-end`: deixa o handoff pendente e pede a nota em segundo plano, sem esperar (RF-112 e RF-136)."""
    session = store.find_session(session_key)
    if session is None:
        return
    create_for_session(store, session, folder)
    drain.enqueue(session.key)
    drain.spawn_drain()


def _log_error() -> None:
    try:
        directory = default_state_dir() / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with Path(directory / "hook.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {traceback.format_exc()}\n")
    except BaseException:  # noqa: BLE001
        return
