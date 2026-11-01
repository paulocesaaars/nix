"""Cenários de `bdd/` sobre o `nix ui`: HU-08."""

from __future__ import annotations

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
