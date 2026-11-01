"""Cenário de `bdd/` sobre o painel do Mega Brain: HU-22.1."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.web.conftest import WebClient

from nix.core.brain.events import SessionEvent, find_project
from nix.core.brain.store import BrainStore


def _remember(tmp_path: Path, name: str) -> None:
    folder = tmp_path / name
    folder.mkdir()
    (folder / ".git").mkdir()
    key, folder_name = find_project(str(folder))
    BrainStore().record(
        SessionEvent(
            id=f"evt-{name}",
            agent="claude",
            session_id=f"s-{name}",
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


@pytest.mark.bdd("HU-22.1")
def test_panel_filters_projects_by_name(client: WebClient, tmp_path: Path) -> None:
    for name in ("alfa", "beta", "gama"):
        _remember(tmp_path, name)

    page = client.get("/brain", params={"q": "alf"})

    assert page.status_code == 200
    assert 'data-project="alfa"' in page.text
    assert 'data-project="beta"' not in page.text
    assert 'data-project="gama"' not in page.text
