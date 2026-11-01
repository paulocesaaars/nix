"""Cenários de `bdd/` sobre o `nix ui`: HU-08."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from nix.cli.app import app

runner = CliRunner()


@pytest.mark.bdd("HU-08.2")
def test_ui_without_init_asks_to_init(monkeypatch: pytest.MonkeyPatch) -> None:
    started = {"serve": False}

    def _serve(**kwargs: object) -> None:
        started["serve"] = True

    monkeypatch.setattr("nix.cli.commands.ui_cmd.serve", _serve)

    result = runner.invoke(app, ["ui"])

    assert result.exit_code == 1, result.output
    assert "nix init" in result.output
    assert started["serve"] is False


class _TtyRunner(CliRunner):
    """O Typer troca o stdin; este devolve um terminal, como quem digitou `nix`."""

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


def test_bare_nix_in_a_terminal_opens_the_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = {"browser": None}

    def _serve(**kwargs: object) -> None:
        opened["browser"] = kwargs.get("open_browser")

    monkeypatch.setattr("nix.cli.commands.ui_cmd.serve", _serve)
    result = _TtyRunner().invoke(app, [])

    assert result.exit_code == 0, result.output
    assert opened["browser"] is True


def test_bare_nix_without_terminal_starts_the_mcp_server(monkeypatch: pytest.MonkeyPatch) -> None:
    started = {"server": False}

    def _run() -> None:
        started["server"] = True

    monkeypatch.setattr("nix.mcp.server.run_server", _run)
    result = runner.invoke(app, [])

    assert result.exit_code == 0, result.output
    assert started["server"] is True
