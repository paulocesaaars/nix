"""Cenários de `bdd/` do instalador de hooks: HU-17.5, HU-17.6 e HU-17.7."""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nix.cli.agents import project_root
from nix.cli.app import app
from nix.config.editor import set_value
from nix.core.admin import agent_hooks
from nix.core.brain.agents import AGENTS
from nix.core.brain.store import BrainStore

runner = CliRunner()

_REMOVED = ("gemini", "opencode", "kimi", "kiro", "grok", "antigravity", "devin", "devin-desktop")
_FOUR_FILES = {
    "cursor": ".cursor/hooks.json",
    "copilot": ".github/hooks/nix.json",
    "claude": ".claude/settings.local.json",
    "codex": ".codex/hooks.json",
}
_ACCEPTED = "cursor, copilot, claude, codex"


class _PromptRunner(CliRunner):
    """O Typer monta o stdin com isatty() falso; o install só explica num terminal."""

    @contextlib.contextmanager
    def isolation(
        self,
        input: str | bytes | None = None,
        env: Any = None,
        color: bool = False,
    ) -> Iterator[tuple[Any, Any, Any]]:
        with super().isolation(input=input, env=env, color=color) as streams:
            raw = sys.stdin

            class _TtyStdin:
                def isatty(self) -> bool:
                    return True

                def __getattr__(self, name: str) -> Any:
                    return getattr(raw, name)

            sys.stdin = _TtyStdin()  # type: ignore[assignment]
            try:
                yield streams
            finally:
                sys.stdin = raw


prompt_runner = _PromptRunner()


def _text(result: Any) -> str:
    stderr = getattr(result, "stderr", "") or ""
    return " ".join(f"{result.output}{stderr}".split())


def _repo(tmp_path: Path) -> Path:
    folder = tmp_path / "repo"
    folder.mkdir()
    (folder / ".git").mkdir()
    return folder


def _json_files(folder: Path) -> set[str]:
    return {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*.json")
        if ".git" not in path.parts
    }


@pytest.mark.bdd("HU-17.5")
def test_install_explains_choices_before_writing(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    set_value("brain", "wiki", "Default", source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("nix.cli.commands.brain_cmds._hook_exe", lambda: "C:/nix/nix.exe")

    result = prompt_runner.invoke(app, ["brain", "hooks", "install"], input="project\ny\nn\n")

    text = _text(result)
    assert result.exit_code == 0, text
    assert f"um cliente, alguns ou os {len(AGENTS)} clientes" in text
    assert "conta inteira" in text
    assert "só o repositório" in text
    assert "Nada foi escrito" in text
    assert _json_files(repo) == set()

    missing_scope = runner.invoke(app, ["brain", "hooks", "install"])
    scope_text = _text(missing_scope)
    assert missing_scope.exit_code == 1, scope_text
    assert "--scope" in scope_text

    missing_who = runner.invoke(app, ["brain", "hooks", "install", "--scope", "project"])
    who_text = _text(missing_who)
    assert missing_who.exit_code == 1, who_text
    assert "--agent" in who_text
    assert "--all" in who_text
    assert _json_files(repo) == set()


@pytest.mark.bdd("HU-17.6")
def test_all_installs_only_the_four_clients(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    repo = _repo(tmp_path)
    monkeypatch.setattr("nix.cli.commands.brain_cmds._hook_exe", lambda: "C:/nix/nix.exe")
    assert agent_hooks.CONFIRMED_CLIENTS == ("cursor", "copilot", "claude", "codex")
    assert set(_REMOVED).isdisjoint(AGENTS)

    args = ["brain", "hooks", "install", "--all", "--scope", "project", "--yes", "--project", str(repo)]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, _text(first)
    assert _json_files(repo) == set(_FOUR_FILES.values())

    codex = json.loads((repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    events = codex["hooks"]
    for name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop", "SessionEnd"):
        command = events[name][0]["hooks"][0]["command"]
        assert "--agent codex" in command
    assert "session-start" in events["SessionStart"][0]["hooks"][0]["command"]

    second = runner.invoke(app, args)
    assert second.exit_code == 0, _text(second)
    again = json.loads((repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert len(again["hooks"]["SessionStart"]) == 1

    for name in _REMOVED:
        refused = runner.invoke(
            app,
            ["brain", "hooks", "install", "--scope", "project", "--agent", name, "--yes", "--project", str(repo)],
        )
        refused_text = _text(refused)
        assert refused.exit_code == 1, refused_text
        assert name in refused_text
        assert _ACCEPTED in refused_text
    assert _json_files(repo) == set(_FOUR_FILES.values())


@pytest.mark.bdd("HU-17.7")
def test_unconfirmed_global_hook_writes_no_file(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    repo = _repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(agent_hooks.Path, "home", lambda: home)
    monkeypatch.setattr("nix.cli.commands.brain_cmds._hook_exe", lambda: "C:/nix/nix.exe")
    assert agent_hooks.spec_for("copilot").global_rel == ""

    result = runner.invoke(
        app,
        [
            "brain",
            "hooks",
            "install",
            "--scope",
            "global",
            "--agent",
            "copilot",
            "--yes",
            "--project",
            str(repo),
        ],
    )

    text = _text(result)
    assert result.exit_code == 0, text
    assert "captura parcial" in text
    assert "Nenhum arquivo de hook" in text
    assert _json_files(repo) == set()
    assert list(home.rglob("*")) == []


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(agent_hooks.Path, "home", lambda: home)
    return home


def _kept_project_hook(repo: Path) -> tuple[Path, bytes]:
    """Arquivo do repositório que o escopo global não pode alterar."""
    marker = repo / ".cursor" / "hooks.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"keep": true}\n', encoding="utf-8")
    return marker, marker.read_bytes()


def test_global_hook_install_remove_and_status_use_home(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    repo = _repo(tmp_path)
    home = _home(tmp_path, monkeypatch)
    marker, original = _kept_project_hook(repo)
    monkeypatch.setattr("nix.cli.commands.brain_cmds._hook_exe", lambda: "C:/nix/nix.exe")
    install_args = [
        "brain",
        "hooks",
        "install",
        "--scope",
        "global",
        "--agent",
        "cursor",
        "--yes",
        "--project",
        str(repo),
    ]

    installed = runner.invoke(app, install_args)
    installed_text = _text(installed)
    assert installed.exit_code == 0, installed_text
    global_file = home / ".cursor" / "hooks.json"
    assert global_file.is_file()
    assert "--agent cursor" in global_file.read_text(encoding="utf-8")
    assert marker.read_bytes() == original
    assert _json_files(repo) == {".cursor/hooks.json"}

    root, key = project_root(str(repo))
    cursor = next(item for item in agent_hooks.status(root, key, BrainStore()) if item.spec.key == "cursor")
    assert cursor.state == "ativo"
    assert cursor.hint == ""
    shown = runner.invoke(app, ["brain", "hooks", "status", "--project", str(repo)])
    shown_text = _text(shown)
    assert shown.exit_code == 0, shown_text
    assert "desalinhado" not in shown_text
    assert "--scope project" not in shown_text

    removed = runner.invoke(
        app,
        ["brain", "hooks", "remove", "--scope", "global", "--agent", "cursor", "--project", str(repo)],
    )
    removed_text = _text(removed)
    assert removed.exit_code == 0, removed_text
    assert not global_file.exists()
    assert marker.read_bytes() == original
    after = next(item for item in agent_hooks.status(root, key, BrainStore()) if item.spec.key == "cursor")
    assert after.state == "inativo"


def test_global_hook_without_file_is_not_a_project_mismatch(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    repo = _repo(tmp_path)
    home = _home(tmp_path, monkeypatch)
    _kept_project_hook(repo)
    monkeypatch.setattr("nix.cli.commands.brain_cmds._hook_exe", lambda: "C:/nix/nix.exe")

    installed = runner.invoke(
        app,
        [
            "brain",
            "hooks",
            "install",
            "--scope",
            "global",
            "--agent",
            "cursor",
            "--yes",
            "--project",
            str(repo),
        ],
    )
    assert installed.exit_code == 0, _text(installed)
    global_file = home / ".cursor" / "hooks.json"
    global_file.unlink()

    root, key = project_root(str(repo))
    cursor = next(item for item in agent_hooks.status(root, key, BrainStore()) if item.spec.key == "cursor")
    assert cursor.state == "desalinhado"
    assert "global" in cursor.hint
    assert "--scope global" in cursor.hint
    assert "project" not in cursor.hint


def test_project_hook_without_file_cites_project_scope(
    configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del configured
    _home(tmp_path, monkeypatch)
    repo = _repo(tmp_path)
    root, key = project_root(str(repo))
    BrainStore().register_hook(
        scope="project",
        agent="claude",
        project_key=key,
        hook_file=".claude/settings.local.json",
    )

    claude = next(item for item in agent_hooks.status(root, key, BrainStore()) if item.spec.key == "claude")

    assert claude.state == "desalinhado"
    assert "project" in claude.hint
    assert "--scope project" in claude.hint
    assert "global" not in claude.hint
