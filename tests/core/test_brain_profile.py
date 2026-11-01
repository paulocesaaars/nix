"""Cenários de `bdd/` sobre perfil, mensagens e tokens: HU-19 a HU-21."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.editor import set_value
from nix.config.loader import load_config
from nix.core.brain import hook_entry
from nix.core.brain.events import find_project
from nix.core.brain.store import BrainStore
from nix.core.brain.tokens import report
from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool

runner = CliRunner()


def _project(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    (folder / ".git").mkdir()
    return folder


def _enable() -> None:
    set_value("brain", "wiki", "Default", source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)


def _emit(
    monkeypatch: pytest.MonkeyPatch,
    folder: Path,
    kind: str,
    session_id: str,
    payload: dict[str, object],
) -> None:
    body = {"cwd": str(folder), "session_id": session_id, **payload}
    monkeypatch.setattr(hook_entry, "_read_payload", lambda: body)
    assert hook_entry.main(["--event", kind, "--agent", "claude"]) == 0


@pytest.mark.bdd("HU-19.1")
def test_profile_learns_pnpm_from_two_projects(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable()
    BrainStore().register_hook(scope="global", agent="claude")
    first = _project(tmp_path, "alfa")
    second = _project(tmp_path, "beta")
    _emit(monkeypatch, first, "user-prompt", "s-alfa", {"prompt": "sempre use pnpm"})
    _emit(monkeypatch, second, "user-prompt", "s-beta", {"prompt": "sempre use pnpm"})

    result = runner.invoke(app, ["brain", "profile", "rebuild"])
    assert result.exit_code == 0, result.output

    rows = BrainStore().list_profile("active")
    assert len(rows) == 1
    assert rows[0].page_path == "profile/tools/pnpm.md"
    assert "pnpm" in rows[0].sentence
    evidence = BrainStore().profile_evidence(rows[0].id)
    projects = {project for project, _quote in evidence}
    assert find_project(str(first))[0] in projects
    assert find_project(str(second))[0] in projects
    page = configured / "profile" / "tools" / "pnpm.md"
    text = page.read_text(encoding="utf-8")
    assert "alfa" in text
    assert "beta" in text


@pytest.mark.bdd("HU-19.2")
def test_forgotten_profile_entry_does_not_return(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable()
    BrainStore().register_hook(scope="global", agent="claude")
    first = _project(tmp_path, "alfa")
    second = _project(tmp_path, "beta")
    _emit(monkeypatch, first, "user-prompt", "s-alfa", {"prompt": "sempre use pnpm"})
    _emit(monkeypatch, second, "user-prompt", "s-beta", {"prompt": "sempre use pnpm"})
    assert runner.invoke(app, ["brain", "profile", "rebuild"]).exit_code == 0

    forgotten = runner.invoke(app, ["brain", "profile", "forget", "tools/pnpm.md"])
    assert forgotten.exit_code == 0, forgotten.output
    again = runner.invoke(app, ["brain", "profile", "rebuild"])
    assert again.exit_code == 0, again.output

    assert BrainStore().list_profile("active") == []
    saved = BrainStore().profile_by_path("profile/tools/pnpm.md")
    assert saved is not None
    assert saved.status == "tombstone"
    assert not (configured / "profile" / "tools" / "pnpm.md").exists()


@pytest.mark.bdd("HU-20.1")
def test_message_pop_delivers_once(configured: Path, tmp_path: Path) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    host = RuntimeHost(load_config())
    try:
        call_tool(
            host,
            "brain_message_send",
            {"project": project, "text": "segue com o cadastro", "recipient": "codex"},
        )
        first = call_tool(host, "brain_message_pop", {"project": project})
        second = call_tool(host, "brain_message_pop", {"project": project})
    finally:
        host.close()

    assert first["delivered"] is True
    assert first["text"] == "segue com o cadastro"
    assert second["delivered"] is False


@pytest.mark.bdd("HU-20.2")
def test_briefing_warns_about_waiting_messages(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    BrainStore().register_hook(scope="global", agent="claude")
    BrainStore().send_message(project, "olho na fila", "claude")

    _emit(monkeypatch, folder, "session-start", "nova", {})

    captured = capsys.readouterr().out
    assert "1" in captured
    assert "mensagem" in captured


@pytest.mark.bdd("HU-21.1")
def test_repeated_response_id_counts_once(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    BrainStore().register_hook(scope="global", agent="claude")
    usage = {"response_id": "resp-1", "usage": {"input_tokens": 10, "output_tokens": 4}}
    _emit(monkeypatch, folder, "stop", "sessao", usage)
    _emit(
        monkeypatch,
        folder,
        "stop",
        "sessao",
        {"response_id": "resp-1", "usage": {"input_tokens": 99, "output_tokens": 99}},
    )

    text = report(BrainStore().sessions_for(project)[0].key)
    assert "10 entrada" in text
    assert "4 saída" in text
    assert "99" not in text


@pytest.mark.bdd("HU-21.2")
def test_agent_without_usage_is_unknown(configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    BrainStore().register_hook(scope="global", agent="claude")
    _emit(monkeypatch, folder, "user-prompt", "sem-uso", {"prompt": "só um pedido"})

    assert report(BrainStore().sessions_for(project)[0].key) == "desconhecido"
