"""Cenários de `bdd/` sobre briefing e handoff: HU-18."""

from __future__ import annotations

from pathlib import Path

import pytest

from nix.config.editor import set_value
from nix.config.loader import load_config
from nix.core.brain import hook_entry
from nix.core.brain.events import find_project
from nix.core.brain.store import BrainStore
from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool


def _project(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    (folder / ".git").mkdir()
    return folder


def _enable() -> RuntimeHost:
    set_value("brain", "wiki", "Default", source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)
    return RuntimeHost(load_config())


def _emit(monkeypatch: pytest.MonkeyPatch, folder: Path, kind: str, session_id: str, **payload: object) -> None:
    body = {"cwd": str(folder), "session_id": session_id, **payload}
    monkeypatch.setattr(hook_entry, "_read_payload", lambda: body)
    assert hook_entry.main(["--event", kind, "--agent", "claude"]) == 0


@pytest.mark.bdd("HU-18.1")
def test_session_start_shows_handoff_without_consuming(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    BrainStore().register_hook(scope="global", agent="claude")
    BrainStore().create_handoff(project, "", "retomar-cep-nix no cadastro")

    _emit(monkeypatch, folder, "session-start", "nova")

    captured = capsys.readouterr().out
    assert "retomar-cep-nix" in captured
    assert "histórico" in captured
    assert BrainStore().offered_handoff(project) is not None


@pytest.mark.bdd("HU-18.2")
def test_accept_claims_handoff_once(configured: Path, tmp_path: Path) -> None:
    del configured
    host = _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    try:
        call_tool(host, "brain_handoff_create", {"project": project, "text": "texto-unico-handoff"})
        first = call_tool(host, "brain_handoff_accept", {"project": project, "agent": "claude"})
        second = call_tool(host, "brain_handoff_accept", {"project": project, "agent": "cursor"})
    finally:
        host.close()

    assert first["accepted"] is True
    assert first["text"] == "texto-unico-handoff"
    assert second["accepted"] is False
    assert second["claimed_by"] == "claude"
    assert "claude" in str(second["message"])
    assert "reivindic" in str(second["message"])


@pytest.mark.bdd("HU-18.3")
def test_briefing_warns_about_interrupted_session(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    BrainStore().register_hook(scope="global", agent="claude")
    _emit(monkeypatch, folder, "user-prompt", "antiga-17", prompt="pedido que ficou aberto")
    capsys.readouterr()

    _emit(monkeypatch, folder, "session-start", "nova-18")

    captured = capsys.readouterr().out
    assert "antiga-17" in captured
    assert "interrompida" in captured
