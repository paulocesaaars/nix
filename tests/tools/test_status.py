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
    wikis = status["wikis"]
    assert isinstance(wikis, list) and len(wikis) == 1
    row = wikis[0]
    assert isinstance(row, dict)
    assert row["stale"] is True
    assert isinstance(row["stale_reason"], str)
    assert "diferentes da versão indexada" in row["stale_reason"]
    assert "edições feitas fora do Nix" in row["stale_reason"]
    assert embed_calls == []


def test_write_through_does_not_mark_the_index_stale(configured: Path, host: RuntimeHost) -> None:
    del configured
    call_tool(host, "sync_index", {})
    created = call_tool(
        host,
        "create_note",
        {"rel_path": "Inbox/nova.md", "content": "# Nova\n\nGravada pelo Nix.\n"},
    )

    assert isinstance(created, dict)
    assert created["indexed"] is True
    row = _status_row(host)
    assert row["stale"] is False
    assert row["stale_reason"] is None


def test_older_external_edit_stays_stale_after_a_newer_indexed_note(configured: Path, host: RuntimeHost) -> None:
    call_tool(host, "sync_index", {})
    call_tool(
        host,
        "create_note",
        {"rel_path": "Inbox/nova.md", "content": "# Nova\n\nGravada pelo Nix.\n"},
    )
    _touch(configured / "Inbox" / "reuniao.md", "# Reunião\n\nEditado fora do Nix.\n")

    row = _status_row(host)
    assert row["stale"] is True
    assert isinstance(row["stale_reason"], str)
    assert "diferentes da versão indexada" in row["stale_reason"]


def test_doctor_index_warning_states_the_action(configured: Path, host: RuntimeHost) -> None:
    from nix.core.admin.doctor import build_doctor_report

    call_tool(host, "sync_index", {})
    _touch(configured / "Inbox" / "reuniao.md", "# Reunião\n\nEditado fora do Nix.\n")
    status = host.resolve("Default").status()

    report = build_doctor_report(inspect_index=False, wiki_statuses=[("Default", status, None)])

    check = next(item for item in report.checks if item.label == "Índice Default")
    assert check.level == "warn"
    assert "stale=" not in check.message
    assert "diferentes da versão indexada" in check.message
    assert "nix sync --wiki Default" in check.message


def _status_row(host: RuntimeHost) -> dict[str, object]:
    status = call_tool(host, "index_status", {})
    assert isinstance(status, dict)
    wikis = status["wikis"]
    assert isinstance(wikis, list) and len(wikis) == 1
    row = wikis[0]
    assert isinstance(row, dict)
    return row
