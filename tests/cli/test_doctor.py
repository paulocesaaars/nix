"""Cenários de `bdd/` sobre o `nix doctor`: HU-01."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nix.cli.app import app

runner = CliRunner()

# O painel quebra o caminho longo e desenha a borda no meio da linha.
_BOX = set("│┌┐└┘─╭╮╯╰├┤┬┴┼━┃┏┓┗┛┣┫┳┻╋")


def _flat(text: str) -> str:
    return "".join(char for char in text if not char.isspace() and char not in _BOX)


@pytest.mark.bdd("HU-01.6")
def test_doctor_points_at_missing_vault(configured: Path) -> None:
    expected = configured.resolve().as_posix()
    shutil.rmtree(configured)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    # Aviso de import no ambiente pode aparecer; o que o cenário pede é o vault.
    flat = _flat(result.output)
    assert "Default" in result.output
    assert expected in flat, flat
    assert "não existe".replace(" ", "") in flat, flat
