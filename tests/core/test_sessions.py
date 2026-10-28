"""Cenários de `bdd/` sobre sessões dos agentes: HU-15."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.editor import set_value
from nix.config.loader import load_config
from nix.config.session_defaults import DEFAULT_FOLDER
from nix.core.errors import ConfigError
from nix.core.runtime import RuntimeHost
from nix.core.sessions import hook_entry
from nix.core.sessions.events import SessionEvent, find_project
from nix.core.sessions.store import SessionStore
from nix.core.tools.registry import active_specs, call_tool

runner = CliRunner()
_TOKEN = "zxq-sessao-oculta"


def _project(tmp_path: Path) -> Path:
    folder = tmp_path / "obra"
    folder.mkdir()
    (folder / ".git").mkdir()
    return folder


def _event(
    project: str,
    *,
    kind: str,
    text: str = "",
    tool: str = "",
    target: str = "",
    session_id: str = "abc123",
) -> SessionEvent:
    return SessionEvent(
        id=f"{session_id}:{kind}:{tool}:{text[:24]}",
        agent="claude",
        session_id=session_id,
        project=project,
        project_name="obra",
        cwd=project,
        type=kind,
        ts="2026-10-28T12:00:00+00:00",
        tool=tool,
        target=target,
        text=text,
        is_error=False,
    )


def _enable_sessions() -> RuntimeHost:
    set_value("sessions", "enabled", True, source="cli", persist=True)
    return RuntimeHost(load_config())


@pytest.mark.bdd("HU-15.1")
def test_hook_discards_event_without_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _project(tmp_path)
    monkeypatch.setattr(
        hook_entry,
        "_read_payload",
        lambda: {"session_id": "s1", "cwd": str(folder), "prompt": "continuar daqui"},
    )

    assert hook_entry.main(["--event", "user-prompt", "--agent", "cursor"]) == 0
    assert SessionStore().list_sessions() == []


@pytest.mark.bdd("HU-15.2")
def test_hook_records_event_when_project_has_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _project(tmp_path)
    project, _name = find_project(str(folder))
    SessionStore().register_project(project, "cursor")
    monkeypatch.setattr(
        hook_entry,
        "_read_payload",
        lambda: {"session_id": "s1", "cwd": str(folder), "prompt": "continuar daqui"},
    )

    assert hook_entry.main(["--event", "user-prompt", "--agent", "cursor"]) == 0

    rows = SessionStore().list_sessions(project=project)
    assert len(rows) == 1
    assert rows[0].agent == "cursor"


@pytest.mark.bdd("HU-15.3")
def test_handoff_is_delivered_once(configured: Path, tmp_path: Path) -> None:
    folder = _project(tmp_path)
    project, _name = find_project(str(folder))
    store = SessionStore()
    store.record(_event(project, kind="user-prompt", text="terminar o índice"))
    host = _enable_sessions()
    try:
        first = call_tool(host, "session_handoff", {"accept": True, "agent": "cursor", "project": project})
        second = call_tool(host, "session_handoff", {"accept": True, "agent": "copilot", "project": project})
    finally:
        host.close()

    assert isinstance(first, dict)
    assert first["state"] == "consumido"
    assert "histórico" in str(first["handoff"])
    assert isinstance(second, dict)
    assert second["handoff"] is None


@pytest.mark.bdd("HU-15.4")
def test_read_session_marks_tool_as_already_executed(configured: Path, tmp_path: Path) -> None:
    folder = _project(tmp_path)
    project, _name = find_project(str(folder))
    store = SessionStore()
    store.record(_event(project, kind="user-prompt", text="buscar a nota"))
    store.record(_event(project, kind="post-tool", tool="search_notes", target="Inbox/reuniao.md", text="ok"))
    host = _enable_sessions()
    try:
        found = call_tool(host, "read_session", {"session": "claude:abc123", "project": project})
    finally:
        host.close()

    assert isinstance(found, dict)
    events = found["events"]
    assert isinstance(events, list)
    tools = [item for item in events if isinstance(item, dict) and item.get("tool") == "search_notes"]
    assert tools and tools[0]["state"] == "já executada"
    assert "histórico" in str(found["note"])


@pytest.mark.bdd("HU-15.5")
def test_search_hides_session_folder(configured: Path) -> None:
    note = configured / DEFAULT_FOLDER / "oculta.md"
    note.parent.mkdir(parents=True)
    note.write_text(f"# Sessão\n\nO token exclusivo é {_TOKEN}.\n", encoding="utf-8")
    host = _enable_sessions()
    try:
        call_tool(host, "sync_index", {})
        found = call_tool(host, "search_notes", {"query": _TOKEN, "top_k": 10})
    finally:
        host.close()

    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list)
    assert not any(isinstance(row, dict) and str(row.get("rel_path", "")).startswith(DEFAULT_FOLDER) for row in results)


@pytest.mark.bdd("HU-15.6")
def test_search_includes_session_folder_when_asked(configured: Path) -> None:
    note = configured / DEFAULT_FOLDER / "oculta.md"
    note.parent.mkdir(parents=True)
    note.write_text(f"# Sessão\n\nO token exclusivo é {_TOKEN}.\n", encoding="utf-8")
    host = _enable_sessions()
    try:
        call_tool(host, "sync_index", {})
        found = call_tool(host, "search_notes", {"query": _TOKEN, "folder": DEFAULT_FOLDER, "top_k": 10})
    finally:
        host.close()

    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list) and results
    assert any(isinstance(row, dict) and str(row.get("rel_path", "")).startswith(DEFAULT_FOLDER) for row in results)


@pytest.mark.bdd("HU-15.7")
def test_session_tools_stay_hidden_when_disabled(configured: Path) -> None:
    names = {spec.name for spec in active_specs(False)}
    assert "list_sessions" not in names
    assert "search_notes" in names
    host = RuntimeHost(load_config())
    try:
        with pytest.raises(ConfigError, match="sessions.enabled"):
            call_tool(host, "list_sessions", {})
    finally:
        host.close()


@pytest.mark.bdd("HU-15.8")
def test_skills_install_and_remove_only_nix_skill(configured: Path, tmp_path: Path) -> None:
    root = _project(tmp_path)
    foreign = root / ".agents" / "skills" / "commitar"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("# commitar\n", encoding="utf-8")

    installed = runner.invoke(
        app,
        ["skills", "install", "--agent", "cursor", "--yes", "--project", str(root)],
    )
    assert installed.exit_code == 0, installed.output
    skill = root / ".agents" / "skills" / "sessoes-nix"
    assert (skill / "SKILL.md").is_file()
    assert (skill / ".nix-skill").read_text(encoding="utf-8") == "sessoes-nix\n"

    removed = runner.invoke(app, ["skills", "remove", "--agent", "cursor", "--project", str(root)])
    assert removed.exit_code == 0, removed.output
    assert not skill.exists()
    assert (foreign / "SKILL.md").is_file()
