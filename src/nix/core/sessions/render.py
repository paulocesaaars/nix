"""Nota Markdown de uma sessão no vault (RF-100 a RF-105 e RF-109).

A nota é gravada pelo `VaultWriter` do runtime, com backup e write-through.
Cada turno é uma seção `##` e os novos ficam no fim, para as fronteiras dos
chunks dos turnos antigos não se deslocarem quando a nota cresce.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from nix.core.errors import PathEscapeError, VaultError
from nix.core.runtime import Runtime
from nix.core.sessions import paths
from nix.core.sessions.agents import AGENT_LABELS
from nix.core.sessions.handoff import build_text
from nix.core.sessions.store import EventRow, SessionRow, SessionStore

_SESSION_ID_LINE = re.compile(r'(?m)^session_id:\s*"?([^"\r\n]+?)"?\s*$')


@dataclass(frozen=True)
class RenderResult:
    rel_path: str
    vault: str
    written: bool
    chunks_indexed: int
    message: str


def note_rel_path(folder: str, session: SessionRow) -> str:
    return paths.note_rel_path(folder, session.project_name, session.started, session.agent, session.short_id)


def build_note(
    session: SessionRow,
    events: list[EventRow],
    *,
    note_path: str,
    max_bytes: int,
) -> str:
    handoff = build_text(session, events, note_path)
    turns = _turns(events)
    label = AGENT_LABELS.get(session.agent, session.agent)
    header = _frontmatter(session) + f"# Sessão {label} · {session.short_id}\n\n"
    handoff_block = "## Handoff\n\n" + _quote(handoff) + "\n\n"

    # Os tamanhos saem uma vez só: recompor o corpo a cada turno descartado seria quadrático.
    fixed = len((header + handoff_block).encode("utf-8"))
    remaining = sum(len(turn.encode("utf-8")) for turn in turns)
    dropped = 0
    while dropped < len(turns):
        if fixed + len(_dropped_notice(dropped, session).encode("utf-8")) + remaining <= max_bytes:
            break
        remaining -= len(turns[dropped].encode("utf-8"))
        dropped += 1
    body = header + handoff_block + _dropped_notice(dropped, session) + "".join(turns[dropped:])
    return body if body.endswith("\n") else body + "\n"


def _dropped_notice(dropped: int, session: SessionRow) -> str:
    if not dropped:
        return ""
    return (
        f"> Os {dropped} turnos mais antigos ficaram só em `sessions.db`. "
        f"Veja com `nix session show {session.short_id}`.\n\n"
    )


def render_session(
    runtime: Runtime,
    store: SessionStore,
    session: SessionRow,
    *,
    folder: str,
    max_bytes: int,
) -> RenderResult:
    """Grava ou atualiza a nota da sessão. Não reindexa se o texto não mudou."""
    rel = note_rel_path(folder, session)
    events = store.events_for(session.key)
    content = build_note(session, events, note_path=rel, max_bytes=max_bytes)

    try:
        dest = runtime.writer.resolve(rel)
    except PathEscapeError as exc:
        raise _folder_error(folder, runtime.vault.name, exc) from exc
    if dest.is_file():
        current = dest.read_text(encoding="utf-8")
        _assert_ours(current, session, rel)
        if current.replace("\r\n", "\n") == content:
            store.mark_rendered(session.key, rel, runtime.vault.name)
            return RenderResult(rel, runtime.vault.name, False, 0, "A nota já estava atualizada.")
    try:
        written = runtime.writer.create_note(rel, content, overwrite=True, confirm=True)
    except PathEscapeError as exc:
        raise _folder_error(folder, runtime.vault.name, exc) from exc
    result = runtime.writeback.after_write(written)
    store.mark_rendered(session.key, rel, runtime.vault.name)
    return RenderResult(rel, runtime.vault.name, True, result.chunks_indexed, result.message)


def _assert_ours(current: str, session: SessionRow, rel: str) -> None:
    """RF-105: só sobrescreve nota com `session_id` gravado pela Nix para esta sessão."""
    match = _SESSION_ID_LINE.search(current[:2000])
    if match is None or match.group(1).strip() != session.session_id:
        raise VaultError(
            f"A nota {rel} já existe e não foi gravada pela Nix para esta sessão. "
            "Mova ou renomeie a nota, ou mude sessions.folder com `nix config set sessions.folder PASTA`."
        )


def _folder_error(folder: str, vault: str, exc: PathEscapeError) -> VaultError:
    return VaultError(
        f"A pasta de sessões {folder!r} está excluída pelos filtros do vault {vault}, "
        "então a nota não foi gravada. Tire a pasta de vault.exclude ou aponte "
        "`nix config set sessions.folder PASTA` para uma pasta liberada. "
        f"Detalhe: {exc.message}"
    )


def _frontmatter(session: SessionRow) -> str:
    def q(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "---\n"
        f"agent: {session.agent}\n"
        f"session_id: {q(session.session_id)}\n"
        f"project: {q(session.project_name)}\n"
        f"cwd: {q(session.cwd)}\n"
        f"started: {session.started}\n"
        f"updated: {session.updated}\n"
        f"status: {session.status}\n"
        "tags: [nix, sessao]\n"
        "---\n"
    )


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _turns(events: list[EventRow]) -> list[str]:
    groups: list[list[EventRow]] = []
    current: list[EventRow] = []
    for event in events:
        if event.type == "user-prompt" and current:
            groups.append(current)
            current = []
        current.append(event)
    if current:
        groups.append(current)
    # O `session-start` sozinho antes do primeiro pedido não é um turno.
    if groups and all(event.type == "session-start" for event in groups[0]):
        groups = groups[1:]
    return [_turn(index, group) for index, group in enumerate(groups, start=1)]


def _turn(number: int, events: list[EventRow]) -> str:
    first = events[0]
    when = _clock(first.ts)
    lines = [f"## Turno {number} · {when}", ""]
    if first.type == "user-prompt" and first.text.strip():
        lines += ["**Pedido**", "", _quote(first.text.strip()), ""]
    done = {(e.tool, e.target) for e in events if e.type == "post-tool"}
    entries: list[str] = []
    for event in events:
        if event.type == "post-tool":
            entries.append(_tool_line(event, "falhou" if event.is_error else "já executada"))
        elif event.type == "pre-tool" and (event.tool, event.target) not in done:
            entries.append(_tool_line(event, "sem resultado"))
        elif event.type == "compact" and event.text.strip():
            entries.append(f"- compactação do contexto: {_flat(event.text, 300)}")
    if entries:
        lines += ["**Ferramentas**", "", *_collapse(entries), ""]
    if any(e.type == "stop" for e in events):
        lines += ["Resposta concluída.", ""]
    if any(e.type == "session-end" for e in events):
        lines += ["Sessão encerrada.", ""]
    return "\n".join(lines) + "\n"


def _tool_line(event: EventRow, state: str) -> str:
    label = event.tool or "ferramenta"
    target = f" {_flat(event.target, 160)}" if event.target else ""
    line = f"- ({state}) {label}{target}"
    if event.is_error and event.text:
        line += f" — {_flat(event.text, 240)}"
    return line


def _collapse(entries: list[str]) -> list[str]:
    out: list[str] = []
    count = 1
    for index, entry in enumerate(entries):
        nxt = entries[index + 1] if index + 1 < len(entries) else None
        if nxt == entry:
            count += 1
            continue
        out.append(entry if count == 1 else f"{entry} ×{count}")
        count = 1
    return out


def _flat(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _clock(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%H:%M")
    except ValueError:
        return ts[11:16]
