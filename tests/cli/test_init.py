"""Cenários de `bdd/` sobre o `nix init`: HU-01."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.core.admin.vaults import VaultService

runner = CliRunner()


@pytest.mark.bdd("HU-01.2")
def test_init_with_all_options_does_not_prompt(vault: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "--name", "Pessoal", "--vault", str(vault), "--embedding-model", "1"],
    )

    assert result.exit_code == 0, result.output
    vaults = VaultService().list_vaults()
    assert [item.name for item in vaults] == ["Pessoal"]
    assert Path(vaults[0].path) == vault.resolve()
    assert "Configuração concluída" in result.output


@pytest.mark.bdd("HU-01.4")
def test_init_refuses_name_when_vaults_exist(vault: Path, tmp_path: Path) -> None:
    first = runner.invoke(app, ["init", "--vault", str(vault), "--embedding-model", "1"])
    assert first.exit_code == 0, first.output

    again = runner.invoke(app, ["init", "--name", "Outro", "--vault", str(vault)])

    assert again.exit_code != 0
    assert "nix vault add" in again.output
