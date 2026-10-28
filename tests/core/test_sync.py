"""Cenários de `bdd/` sobre a sincronização incremental: HU-03."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nix.core.runtime import RuntimeHost


def _touch(path: Path, text: str) -> None:
    """Grava o texto e avança o mtime, para a mudança ser vista mesmo em disco com timestamp grosso."""
    path.write_text(text, encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))


@pytest.mark.bdd("HU-03.1")
def test_sync_reprocesses_only_changed_notes(configured: Path, host: RuntimeHost) -> None:
    root = configured
    (root / "Extra.md").write_text("# Extra\n\nQuarta nota.\n", encoding="utf-8")
    indexer = host.resolve(None).indexer
    first = indexer.sync()
    assert first.added == 4

    _touch(root / "Inbox/reuniao.md", "# Reunião\n\nTexto novo.\n")
    _touch(root / "Projetos/ViaCEP/api.md", "# API\n\nTexto novo.\n")
    _touch(root / "Diario/2026-10-28.md", "# Diário\n\nTexto novo.\n")
    (root / "Extra.md").unlink()

    second = indexer.sync()

    assert (second.added, second.updated, second.removed, second.skipped) == (0, 3, 1, 0)


@pytest.mark.bdd("HU-03.2")
def test_sync_without_changes_reprocesses_nothing(configured: Path, host: RuntimeHost) -> None:
    indexer = host.resolve(None).indexer
    indexer.sync()

    again = indexer.sync()

    assert (again.added, again.updated, again.removed) == (0, 0, 0)
    assert again.skipped == 3
    assert "0 adicionados" in again.summary_pt()
