"""Monta a página da sessão por regras, sem modelo de linguagem."""

from __future__ import annotations

from nix.core.brain.events import is_edit_tool
from nix.core.brain.paths import session_page_rel
from nix.core.brain.store import ObservationRecord, SessionRecord


def page_path_for(session: SessionRecord) -> str:
    short = session.external_id[:12]
    return session_page_rel(session.project_name, session.started_at, session.agent, short)


def build_session_page(
    session: SessionRecord,
    observations: list[ObservationRecord],
    *,
    tokens_line: str,
) -> tuple[str, dict[str, object]]:
    """Corpo e frontmatter. O writer da wiki acrescenta o bloco YAML."""
    requests = [row.text for row in observations if row.kind == "user-prompt" and row.text]
    files = _changed_files(observations)
    error = _last_error(observations)
    open_item = requests[-1] if requests else ""
    body = "\n".join(
        [
            f"# Sessão {session.started_at[:10]} · {session.agent}",
            "",
            "## Pedidos",
            "",
            *_request_lines(requests),
            "",
            "## Arquivos alterados",
            "",
            *([f"- {path}" for path in files] or ["Nenhum arquivo alterado."]),
            "",
            "## Último erro",
            "",
            error or "nenhum",
            "",
            "## Em aberto",
            "",
            open_item or "nada em aberto",
            "",
            "## Tokens",
            "",
            tokens_line or "desconhecido",
            "",
        ]
    )
    frontmatter: dict[str, object] = {
        "kind": "session",
        "project": session.project_name,
        "agent": session.agent,
        "tags": ["sessao", session.agent],
        "title": f"Sessão {session.started_at[:10]} {session.agent}",
    }
    return body, frontmatter


def _request_lines(requests: list[str]) -> list[str]:
    if not requests:
        return ["Nenhum pedido gravado."]
    lines = [f"- Primeiro: {requests[0]}"]
    recent = requests[-5:]
    if len(requests) > 1:
        lines.append("- Cinco últimos:")
        lines.extend(f"  - {item}" for item in recent)
    if requests[-1] != requests[0]:
        lines.append(f"- Último: {requests[-1]}")
    return lines


def _changed_files(observations: list[ObservationRecord]) -> list[str]:
    found: list[str] = []
    for row in observations:
        if row.kind == "post-tool" and row.target and is_edit_tool(row.tool) and row.target not in found:
            found.append(row.target)
    return found


def _last_error(observations: list[ObservationRecord]) -> str:
    for row in reversed(observations):
        if row.is_error and row.text:
            return row.text
    return ""
