"""Cenários de `bdd/` sobre captura do Mega Brain: HU-17."""

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


def _enable() -> None:
    set_value("brain", "wiki", "Default", source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)


def _emit(monkeypatch: pytest.MonkeyPatch, folder: Path, kind: str, payload: dict[str, object]) -> None:
    body = {"cwd": str(folder), "session_id": "s1", **payload}
    monkeypatch.setattr(hook_entry, "_read_payload", lambda: body)
    assert hook_entry.main(["--event", kind, "--agent", "claude"]) == 0


@pytest.mark.bdd("HU-17.1")
def test_global_hook_captures_repo_without_local_install(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    _enable()
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    BrainStore().register_hook(scope="global", agent="claude")

    _emit(monkeypatch, folder, "user-prompt", {"prompt": "continuar o cadastro"})

    rows = BrainStore().sessions_for(project)
    assert len(rows) == 1
    assert rows[0].agent == "claude"
    assert rows[0].project_key == project


@pytest.mark.bdd("HU-17.2")
def test_project_opt_out_stores_nothing(configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del configured
    _enable()
    BrainStore().register_hook(scope="global", agent="claude")
    folder = _project(tmp_path, "calado")
    project, _name = find_project(str(folder))
    toml = folder / ".nix.toml"
    with toml.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("[capture]\nenabled = false\n")

    _emit(monkeypatch, folder, "user-prompt", {"prompt": "isto não pode entrar"})

    assert BrainStore().sessions_for(project) == []


@pytest.mark.bdd("HU-17.3")
def test_excluded_path_is_dropped(configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del configured
    _enable()
    BrainStore().register_hook(scope="global", agent="claude")
    folder = _project(tmp_path, "cofre")
    project, _name = find_project(str(folder))
    toml = folder / ".nix.toml"
    with toml.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write('[capture]\nexclude = ["segredos/**"]\n')

    _emit(
        monkeypatch,
        folder,
        "post-tool",
        {"tool_name": "Read", "tool_input": {"file_path": "segredos/chave.txt"}},
    )

    assert BrainStore().sessions_for(project) == []


@pytest.mark.bdd("HU-17.4")
def test_session_end_writes_page_and_query_finds_it(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable()
    monkeypatch.setenv("NIX_BRAIN_WORK_INLINE", "1")
    BrainStore().register_hook(scope="global", agent="claude")
    folder = _project(tmp_path, "obra")
    project, _name = find_project(str(folder))
    _emit(monkeypatch, folder, "user-prompt", {"prompt": "primeiro pedido-alfa-nix no cadastro"})
    _emit(monkeypatch, folder, "user-prompt", {"prompt": "segundo pedido-beta-nix para fechar"})
    _emit(monkeypatch, folder, "session-end", {})

    pages = list((configured / "projects" / "obra" / "sessions").glob("*.md"))
    assert pages, "a página da sessão não foi gravada em projects/obra/sessions/"
    text = pages[0].read_text(encoding="utf-8")
    assert "pedido-alfa-nix" in text
    assert "pedido-beta-nix" in text

    host = RuntimeHost(load_config())
    try:
        found = call_tool(host, "brain_query", {"query": "pedido-alfa-nix", "project": project})
    finally:
        host.close()
    paths = [item["path"] for item in found["pages"]]
    assert any("projects/obra/sessions/" in path for path in paths)
