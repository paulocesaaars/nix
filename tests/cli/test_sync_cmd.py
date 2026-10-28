"""Cenários de `bdd/` sobre o `nix sync`: HU-02."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nix.cli.app import app

runner = CliRunner()

_NOTES = ("Inbox/reuniao.md", "Projetos/ViaCEP/api.md", "Diario/2026-10-28.md")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def _indexed() -> dict[str, str]:
    from nix.config.loader import load_config
    from nix.core.index.store import IndexStore

    store = IndexStore(load_config().vault_index_dir() / "index.db")
    try:
        return {str(row["rel_path"]): str(row["status"]) for row in store.list_files()}
    finally:
        store.close()


@pytest.mark.bdd("HU-02.1")
def test_sync_indexes_notes_outside_exclude(configured: Path) -> None:
    ignored = configured / "Templates" / "modelo.md"
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("# Modelo\n\nNota que o vault.exclude deixa de fora.\n", encoding="utf-8")

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0, result.output
    plain = _plain(result.output)
    assert re.search(r"Adicionadas\s+3\b", plain), plain
    assert re.search(r"Atualizadas\s+0\b", plain), plain
    assert re.search(r"Removidas\s+0\b", plain), plain
    assert re.search(r"Concluído em \d+,\d s", plain), plain
    assert "modelo.md" not in plain
    files = _indexed()
    assert files.keys() == set(_NOTES)
    assert set(files.values()) == {"indexed"}


@pytest.mark.bdd("HU-02.2")
def test_sync_shows_progress_for_each_note(configured: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from rich.console import Console

    from nix.cli import render
    from nix.cli.commands import index_cmds

    # O CliRunner não é um TTY e o Rich omite a barra. Só esta chamada força o console.
    # TERM=dumb também segura os quadros do meio; xterm deixa cada nota no fluxo capturado.
    monkeypatch.setattr(
        render,
        "console",
        Console(
            force_terminal=True,
            force_interactive=True,
            width=200,
            theme=render.NIX_THEME,
            _environ={**os.environ, "TERM": "xterm-256color"},
        ),
    )
    opened = index_cmds.sync_progress
    apply = index_cmds.apply_sync_progress

    def _progress() -> Any:
        # O sync cabe num quadro só; sem o refresh automático, cada nota é pintada na hora.
        progress = opened()
        progress.live.auto_refresh = False
        return progress

    def _apply(progress: Any, event: Any) -> None:
        apply(progress, event)
        progress.refresh()

    monkeypatch.setattr(index_cmds, "sync_progress", _progress)
    monkeypatch.setattr(index_cmds, "apply_sync_progress", _apply)

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0, result.output
    plain = _plain(result.output)
    total = len(_NOTES)
    for note in _NOTES:
        assert note in plain, plain
    for step in range(1, total + 1):
        assert f"{step}/{total}" in plain, plain


@pytest.mark.bdd("HU-02.3")
def test_sync_reports_invalid_encoding_and_indexes_the_rest(configured: Path) -> None:
    (configured / "quebrada.md").write_bytes(b"# Nota\n\n\xff\xfe\x00\x81")

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0, result.output
    plain = _plain(result.output)
    assert plain.rindex("Encoding inválido") > plain.rindex("Arquivos")
    files = _indexed()
    assert files["quebrada.md"] == "error"
    for note in _NOTES:
        assert files[note] == "indexed"
