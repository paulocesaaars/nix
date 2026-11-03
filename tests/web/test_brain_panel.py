"""Cenário de `bdd/` sobre o painel do Mega Brain: HU-22.1."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.web.conftest import WebClient

from nix.config.editor import set_value
from nix.config.loader import clear_config_cache, load_config
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


@pytest.mark.bdd("HU-22.3")
def test_panel_changes_brain_state(client: WebClient) -> None:
    wiki = load_config().default_wiki.name
    for enabled in ("true", "false"):
        response = client.post_csrf("/brain/settings", {"brain_wiki": wiki, "enabled": enabled})
        assert response.status_code == 200
        assert load_config().brain.enabled is (enabled == "true")
        assert load_config().brain.wiki == wiki


@pytest.mark.bdd("HU-22.4")
def test_panel_requires_brain_wiki(client: WebClient) -> None:
    page = client.get("/brain/settings")
    assert "Selecione uma wiki" in page.text
    response = client.post_csrf("/brain/settings", {"enabled": "true", "brain_wiki": ""})
    assert response.status_code == 400
    assert not load_config().brain.enabled


@pytest.mark.bdd("HU-22.5")
@pytest.mark.parametrize("locked_field", ["wiki", "enabled"])
def test_environment_locks_only_its_field(
    client: WebClient, monkeypatch: pytest.MonkeyPatch, locked_field: str
) -> None:
    wiki = load_config().default_wiki.name
    monkeypatch.setenv(f"NIX_BRAIN__{locked_field.upper()}", wiki if locked_field == "wiki" else "true")
    clear_config_cache()
    page = client.get("/brain/settings")
    select = page.text.split(f'id="brain-{locked_field}"', 1)[1].split(">", 1)[0]
    assert "disabled" in select
    data = {"enabled": "true"} if locked_field == "wiki" else {"brain_wiki": wiki}
    response = client.post_csrf("/brain/settings", data)
    assert response.status_code == 200
    assert load_config().brain.wiki == wiki
    assert load_config().brain.enabled


@pytest.mark.bdd("HU-22.6")
def test_cli_enable_is_atomic(configured: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from nix.cli.app import app
    from nix.config.store import SettingsStore

    del configured
    wiki = load_config().default_wiki.name
    set_value("brain", "wiki", "", source="cli", persist=True)
    before = SettingsStore().load_overrides()
    monkeypatch.setenv("NIX_BRAIN__ENABLED", "false")
    clear_config_cache()
    result = CliRunner().invoke(app, ["brain", "enable", "--wiki", wiki])
    assert result.exit_code != 0
    assert SettingsStore().load_overrides() == before
