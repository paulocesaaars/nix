"""O session-end do binário leve precisa abrir o nix completo para gravar a página."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nix.config.paths import default_state_dir
from nix.core.brain import worker


def _names() -> tuple[str, str]:
    if sys.platform == "win32":
        return "nix-hook.exe", "nix.exe"
    return "nix-hook", "nix"


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def popen(cmd: list[str], **_kwargs: object) -> None:
        seen.append(list(cmd))

    monkeypatch.setattr(worker, "_packaged", lambda: True)
    monkeypatch.setattr(worker.subprocess, "Popen", popen)
    return seen


def test_packaged_hook_spawns_the_sibling_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hook_name, cli_name = _names()
    hook = tmp_path / hook_name
    cli = tmp_path / cli_name
    hook.write_bytes(b"")
    cli.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(hook)])
    monkeypatch.setattr(sys, "executable", str(hook))
    seen = _capture(monkeypatch)

    worker.schedule("sessao-1")

    assert seen == [[str(cli), "brain", "work", "--session", "sessao-1"]]


def test_packaged_hook_uses_nix_home_without_a_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook_name, cli_name = _names()
    hook = tmp_path / "extract" / hook_name
    hook.parent.mkdir()
    hook.write_bytes(b"")
    home = tmp_path / "home"
    cli = home / "bin" / cli_name
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"")
    monkeypatch.setenv("NIX_HOME", str(home))
    monkeypatch.setattr(sys, "argv", [str(hook)])
    monkeypatch.setattr(sys, "executable", str(hook))
    seen = _capture(monkeypatch)

    worker.schedule("sessao-2")

    assert seen == [[str(cli), "brain", "work", "--session", "sessao-2"]]


def test_packaged_cli_spawns_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _hook_name, cli_name = _names()
    cli = tmp_path / cli_name
    cli.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(cli), "brain", "work"])
    monkeypatch.setattr(sys, "executable", str(cli))
    seen = _capture(monkeypatch)

    worker.schedule("sessao-3")

    assert seen == [[str(cli), "brain", "work", "--session", "sessao-3"]]


def test_missing_cli_is_logged_and_not_spawned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hook_name, cli_name = _names()
    hook = tmp_path / "extract" / hook_name
    hook.parent.mkdir()
    hook.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(hook)])
    monkeypatch.setattr(sys, "executable", str(hook))
    seen = _capture(monkeypatch)

    worker.schedule("sessao-4")

    assert seen == []
    text = (default_state_dir() / "logs" / "brain-hook.log").read_text(encoding="utf-8")
    assert str(hook.parent / cli_name) in text
    assert "NIX_HOME" in text
    assert "instalador" in text
