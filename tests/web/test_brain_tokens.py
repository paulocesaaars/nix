"""Cenários de `bdd/` sobre a aba Tokens do projeto: HU-21.3 e HU-21.4."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.web.conftest import WebClient

from nix.core.brain.events import SessionEvent, find_project
from nix.core.brain.store import BrainStore


def _remember(tmp_path: Path, name: str, agent: str) -> str:
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / ".git").mkdir(exist_ok=True)
    key, folder_name = find_project(str(folder))
    BrainStore().record(
        SessionEvent(
            id=f"evt-{name}-{agent}",
            agent=agent,
            session_id=f"s-{name}-{agent}",
            project=key,
            project_name=folder_name,
            cwd=str(folder),
            type="user-prompt",
            ts="2026-11-01T00:00:00+00:00",
            tool="",
            target="",
            text="pedido",
            is_error=False,
        ),
        folder_name,
    )
    return key


def _usage(project_key: str, agent: str, model: str, incoming: int, outgoing: int) -> None:
    BrainStore().record_tokens(
        response_id=f"{project_key}|{agent}|{model}",
        session_key=f"{project_key}|{agent}:s",
        project_key=project_key,
        agent=agent,
        model=model,
        input_tokens=incoming,
        output_tokens=outgoing,
    )


def _token_rows(html: str) -> list[tuple[str, ...]]:
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", body, flags=re.S):
        cells = [cell.strip() for cell in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
        rows.append(tuple(cells))
    return rows


@pytest.mark.bdd("HU-21.3")
def test_project_tokens_one_line_per_agent(client: WebClient, tmp_path: Path) -> None:
    alfa = _remember(tmp_path, "alfa", "claude")
    _remember(tmp_path, "alfa", "codex")
    _remember(tmp_path, "alfa", "cursor")
    beta = _remember(tmp_path, "beta", "claude")
    _usage(alfa, "claude", "sonnet", 10, 4)
    _usage(alfa, "claude", "opus", 7, 2)
    _usage(alfa, "copilot", "gpt-4o", 1, 2)
    _usage(alfa, "codex", "gpt-5", 3, 1)
    _usage(alfa, "codex", "gpt-5-mini", 8, 9)
    _usage(beta, "claude", "opus", 500, 250)

    page = client.get("/brain/project", params={"project": alfa, "tab": "tokens"})

    assert page.status_code == 200
    assert _token_rows(page.text) == [
        ("Claude Code", "17", "6"),
        ("Codex", "11", "10"),
        ("VS Code", "1", "2"),
        ("Total", "29", "18"),
    ]
    assert "copilot" not in page.text
    assert "cursor" not in page.text
    assert "sonnet" not in page.text
    assert "opus" not in page.text
    assert "gpt-5" not in page.text
    assert "500" not in page.text
    assert "250" not in page.text
    assert "Uso desconhecido" not in page.text


@pytest.mark.bdd("HU-21.4")
def test_project_without_token_numbers_is_unknown(client: WebClient, tmp_path: Path) -> None:
    key = _remember(tmp_path, "vazio", "claude")

    page = client.get("/brain/project", params={"project": key, "tab": "tokens"})

    assert page.status_code == 200
    assert "Uso desconhecido. Nenhum evento trouxe números de tokens." in page.text
    assert "Total" not in page.text
    assert "table-box" not in page.text
    assert "<td>0</td>" not in page.text
