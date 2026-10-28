"""Cenários de `bdd/` sobre o `nix vault`: HU-13."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.loader import clear_config_cache, load_config
from nix.core.index.lock import index_lock

runner = CliRunner()


def _registration() -> list[dict[str, Any]]:
    clear_config_cache()
    rows = [vault.model_dump(mode="json") for vault in load_config().vaults]
    return sorted(rows, key=lambda row: str(row["name"]).casefold())


@pytest.mark.bdd("HU-13.3")
def test_rename_keeps_index_and_asks_for_full_sync(configured: Path) -> None:
    synced = runner.invoke(app, ["sync"])
    assert synced.exit_code == 0, synced.output

    clear_config_cache()
    config = load_config()
    previous_index = config.vault_index_dir()
    index_db = previous_index / "index.db"
    assert index_db.is_file()
    backup = config.vault_backup_dir() / "nota.md"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text("backup", encoding="utf-8")

    result = runner.invoke(app, ["vault", "rename", "Default", "Pessoal"])

    assert result.exit_code == 0, result.output
    assert "nix sync --full --vault Pessoal" in result.output
    assert previous_index.name == "Default"
    assert index_db.is_file()
    assert backup.is_file()
    clear_config_cache()
    renamed = load_config()
    assert renamed.default_vault.name == "Pessoal"
    assert renamed.vault_index_dir() != previous_index
    assert not (renamed.vault_index_dir() / "index.db").exists()
    assert not (renamed.vault_backup_dir() / "nota.md").exists()


@pytest.mark.bdd("HU-13.4")
def test_vault_mutations_wait_for_sync_lock(configured: Path, second_vault: Path, tmp_path: Path) -> None:
    added = runner.invoke(app, ["vault", "add", "Trabalho", str(second_vault)])
    assert added.exit_code == 0, added.output
    other = tmp_path / "outra-pasta"
    other.mkdir()
    before = _registration()

    # A trava é do segundo vault. O padrão continua livre.
    with index_lock("Trabalho"):
        refused = [
            runner.invoke(app, ["vault", "rename", "Trabalho", "Escritorio"]),
            runner.invoke(app, ["vault", "remove", "Trabalho"]),
            runner.invoke(app, ["vault", "path", "Trabalho", str(other)]),
            runner.invoke(app, ["vault", "set", "Trabalho", "follow_symlinks", "true"]),
        ]

    for result in refused:
        assert result.exit_code == 1, result.output
        assert "Trabalho" in result.output
        assert "Espere" in result.output
    assert _registration() == before
