"""Cenários de `bdd/` sobre o índice visto pelas ferramentas: HU-03."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool


def _touch(path: Path, text: str) -> None:
    """Grava o texto e avança o mtime, para a mudança ser vista mesmo em disco com timestamp grosso."""
    path.write_text(text, encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))


@pytest.mark.bdd("HU-03.3")
def test_index_status_reports_stale_without_embedding(
    configured: Path,
    host: RuntimeHost,
    fake_embedder: type,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_tool(host, "sync_index", {})
    _touch(configured / "Inbox" / "reuniao.md", "# Reunião\n\nEditado fora do Nix.\n")

    embed_calls: list[object] = []
    original = fake_embedder.embed

    def spy(self: object, texts: object) -> object:
        embed_calls.append(texts)
        return original(self, texts)

    # O sync acima vetoriza. A espionagem começa só no index_status.
    monkeypatch.setattr(fake_embedder, "embed", spy)
    status = call_tool(host, "index_status", {})

    assert isinstance(status, dict)
    vaults = status["vaults"]
    assert isinstance(vaults, list) and len(vaults) == 1
    row = vaults[0]
    assert isinstance(row, dict)
    assert row["stale"] is True
    assert isinstance(row["stale_reason"], str)
    assert "mais recentes que o último sync" in row["stale_reason"]
    assert embed_calls == []
