"""Cenários de `bdd/` sobre ferramentas sem escolher o vault: HU-09."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import SECOND_VAULT_NAME

from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool


@pytest.mark.bdd("HU-09.1")
def test_read_note_without_vault_uses_the_default(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    host = second_registered
    other = second_vault / "Inbox" / "reuniao.md"
    other.parent.mkdir(parents=True)
    other.write_text("Texto exclusivo do vault Outro.\n", encoding="utf-8")

    read = call_tool(host, "read_note", {"rel_path": "Inbox/reuniao.md"})

    assert isinstance(read, dict)
    assert read["vault"] == "Default"
    content = str(read["content"])
    assert "Decidimos validar CEP" in content
    assert "Texto exclusivo do vault Outro" not in content
    assert content == (configured / "Inbox" / "reuniao.md").read_text(encoding="utf-8")


@pytest.mark.bdd("HU-09.2")
def test_list_vaults_reports_name_path_default_and_staleness(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    host = second_registered
    call_tool(host, "sync_index", {"vault": "Default"})

    listed = call_tool(host, "list_vaults", {})

    assert isinstance(listed, dict)
    rows = listed["vaults"]
    assert isinstance(rows, list)
    by_name = {row["name"]: row for row in rows if isinstance(row, dict)}
    assert set(by_name) == {"Default", SECOND_VAULT_NAME}

    default = by_name["Default"]
    other = by_name[SECOND_VAULT_NAME]
    assert default["path"] == configured.resolve().as_posix()
    assert default["is_default"] is True
    assert default["stale"] is False
    assert other["path"] == second_vault.resolve().as_posix()
    assert other["is_default"] is False
    assert other["stale"] is True
