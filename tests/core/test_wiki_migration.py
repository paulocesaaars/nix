"""Cenários de `bdd/` sobre a troca de vault por wiki: HU-16."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.loader import clear_config_cache, load_config
from nix.config.paths import settings_path
from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool

runner = CliRunner()
_BOX = set("│┌┐└┘─╭╮╯╰├┤┬┴┼━┃┏┓┗┛┣┫┳┻╋")


def _flat(text: str) -> str:
    return "".join(char for char in text if not char.isspace() and char not in _BOX)


def _rewind_to_schema_v2() -> None:
    """Simula um settings.db da versão 2, sem tocar no índice nem nos backups."""
    connection = sqlite3.connect(settings_path())
    try:
        connection.execute("ALTER TABLE wikis RENAME TO vaults")
        connection.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()


@pytest.mark.bdd("HU-16.1")
def test_vaults_table_migrates_and_search_keeps_the_index(configured: Path) -> None:
    host = RuntimeHost(load_config())
    try:
        call_tool(host, "sync_index", {"wiki": "Default"})
    finally:
        host.close()

    _rewind_to_schema_v2()
    clear_config_cache()

    listed = runner.invoke(app, ["wiki", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Default" in listed.output
    assert configured.resolve().as_posix() in _flat(listed.output)

    fresh = RuntimeHost(load_config())
    try:
        found = call_tool(fresh, "search_notes", {"query": "validar CEP", "wiki": "Default", "top_k": 5})
    finally:
        fresh.close()

    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list)
    assert any("CEP" in str(row.get("content", "")) for row in results if isinstance(row, dict))
    clear_config_cache()
    assert load_config().default_wiki.name == "Default"
    assert load_config().default_wiki.path == configured.resolve().as_posix()
