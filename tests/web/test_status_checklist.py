"""Cenários de `bdd/` do caminho inicial no Status: HU-08.13 a HU-08.19 e HU-08.21.

HU-08.20 fica em `tests/web/test_traffic.py`, ao lado do middleware de tools/call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import SECOND_WIKI_NAME
from tests.web.conftest import WebClient
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.editor import history, mark_editor_called, set_value, unset_value
from nix.config.loader import clear_config_cache, env_overrides, load_config
from nix.config.schema import DEFAULT_WIKI_NAME
from nix.config.store import SettingsStore
from nix.core.admin.traffic import TrafficStore
from nix.core.admin.wikis import WikiService
from nix.core.errors import ConfigError
from nix.core.tools.registry import call_tool

runner = CliRunner()

_STALE = "O índice está desatualizado"
_BLOCK = "Para começar"
_SEARCH_PENDING = "Abra o editor e peça para buscar uma nota."
_SEARCH_DONE = "O editor já pediu uma busca."
_SEARCH_TITLE = "Pedir uma busca ao editor"


def _touch(path: Path, text: str) -> None:
    """Grava o texto e avança o mtime, para a mudança ser vista mesmo em disco com timestamp grosso."""
    path.write_text(text, encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))


def _sync(client: WebClient) -> None:
    call_tool(client.gate.host, "sync_index", {})


def _search_call() -> None:
    TrafficStore().record(
        client="editor",
        method="tools/call",
        tool="search_notes",
        arguments=None,
        status="ok",
        duration_ms=1.0,
    )


def _open(client: WebClient, wiki: str | None = None) -> str:
    # O Status é a raiz da interface.
    page = client.get("/") if wiki is None else client.get("/", params={"wiki": wiki})
    assert page.status_code == 200, page.text
    return page.text


def _href(path: str, wiki: str) -> str:
    return f'href="{path}?wiki={wiki}"'


@pytest.mark.bdd("HU-08.13")
def test_status_shows_the_start_path_before_sync_and_search(client: WebClient) -> None:
    html = _open(client)
    name = DEFAULT_WIKI_NAME

    assert _BLOCK in html
    assert f"A wiki padrão é {name}." in html
    assert "Wiki cadastrada" in html
    assert 'class="badge b-ok"' in html
    assert f"A wiki {name} ainda não foi sincronizada." in html
    assert _SEARCH_TITLE in html
    assert _SEARCH_PENDING in html
    assert 'class="badge b-warn"' in html
    assert _href("/wikis", name) in html
    assert _href("/sync", name) in html
    assert _href("/connect", name) in html
    assert _STALE not in html


@pytest.mark.bdd("HU-08.14")
def test_status_hides_the_start_path_after_sync_and_search(client: WebClient) -> None:
    _sync(client)
    _search_call()

    html = _open(client)

    assert _BLOCK not in html


@pytest.mark.bdd("HU-08.15")
def test_status_brings_the_start_path_back_for_an_unsynced_wiki(
    client: WebClient,
    second_wiki: Path,
) -> None:
    _sync(client)
    _search_call()
    WikiService().add(SECOND_WIKI_NAME, second_wiki)

    html = _open(client, SECOND_WIKI_NAME)

    assert _BLOCK in html
    assert f"A wiki {SECOND_WIKI_NAME} ainda não foi sincronizada." in html
    assert _href("/sync", SECOND_WIKI_NAME) in html
    assert _SEARCH_DONE in html
    assert _SEARCH_PENDING not in html


@pytest.mark.bdd("HU-08.16")
def test_stale_index_keeps_the_start_path_hidden(client: WebClient, configured: Path) -> None:
    _sync(client)
    _search_call()
    _touch(configured / "Inbox" / "reuniao.md", "# Reunião\n\nEditado fora do Nix.\n")

    html = _open(client)

    assert _BLOCK not in html
    assert _STALE in html


@pytest.mark.bdd("HU-08.17")
def test_status_names_the_selected_wiki_when_it_is_not_the_default(
    client: WebClient,
    second_wiki: Path,
) -> None:
    WikiService().add(SECOND_WIKI_NAME, second_wiki)

    html = _open(client, SECOND_WIKI_NAME)
    intro = f"Você está em {SECOND_WIKI_NAME}. A padrão é {DEFAULT_WIKI_NAME}."

    assert _BLOCK in html
    assert intro in html
    assert html.index(intro) < html.index("Wiki cadastrada")


@pytest.mark.bdd("HU-08.18")
def test_saved_editor_call_hides_the_start_path_without_traffic(client: WebClient) -> None:
    _sync(client)
    mark_editor_called(source="mcp")

    html = _open(client)

    assert _BLOCK not in html
    assert TrafficStore().recent(1) == []


@pytest.mark.bdd("HU-08.19")
def test_status_backfills_the_editor_mark_from_traffic(client: WebClient) -> None:
    _search_call()
    assert load_config().ui.editor_called is False

    _open(client)

    assert load_config().ui.editor_called is True
    assert _mark_history_rows() == 0


@pytest.mark.bdd("HU-08.21")
def test_status_keeps_the_start_path_until_search_is_asked(client: WebClient) -> None:
    _sync(client)
    assert load_config().ui.editor_called is False
    assert TrafficStore().recent(1) == []

    html = _open(client)
    sync = _step_row(html, "Sincronizar o índice")
    search = _step_row(html, _SEARCH_TITLE)

    assert _BLOCK in html
    assert "feito" in sync
    assert "pendente" not in sync
    assert f"A wiki {DEFAULT_WIKI_NAME} já foi sincronizada." in sync
    assert "pendente" in search
    assert "feito" not in search
    assert _SEARCH_PENDING in search
    assert _SEARCH_DONE not in html
    assert load_config().ui.editor_called is False
    assert TrafficStore().recent(1) == []


def test_editor_mark_stays_out_of_history_and_undo_refuses_it(client: WebClient) -> None:
    mark_editor_called(source="mcp")
    assert load_config().ui.editor_called is True
    assert _mark_history_rows() == 0

    set_value("retrieval", "top_k", 12, source="cli")
    change_id = _insert_mark_history()
    assert history(1)[0].dotted == "retrieval.top_k"
    assert all(row.dotted != "ui.editor_called" for row in history())

    page = client.get("/history")
    assert page.status_code == 200
    assert "editor_called" not in page.text
    listed = runner.invoke(app, ["config", "history"])
    assert listed.exit_code == 0, _cli_text(listed)
    assert "editor_called" not in _cli_text(listed)

    refused = runner.invoke(app, ["config", "set", "ui.editor_called", "true"])
    assert refused.exit_code == 1, _cli_text(refused)
    assert "não existe" in _cli_text(refused)
    assert "nix config list" in _cli_text(refused)
    removed = runner.invoke(app, ["config", "unset", "ui.editor_called"])
    assert removed.exit_code == 1, _cli_text(removed)
    assert "não existe" in _cli_text(removed)
    with pytest.raises(ConfigError, match="não existe") as denied:
        set_value("ui", "editor_called", False, source="cli")
    assert "nix config list" in denied.value.message
    with pytest.raises(ConfigError, match="não existe") as missing:
        unset_value("ui", "editor_called", source="cli")
    assert "nix config list" in missing.value.message

    undone = runner.invoke(app, ["config", "undo", str(change_id)])
    text = _cli_text(undone)
    assert undone.exit_code == 1, text
    assert "não se desfaz por aqui" in text
    assert "nix config list" not in text
    web = client.post_csrf(f"/history/{change_id}/undo")
    assert web.status_code == 200
    assert "não se desfaz por aqui" in web.text
    assert "nix config list" not in web.text
    assert "editor_called" not in web.text
    assert load_config().ui.editor_called is True
    assert load_config().retrieval.top_k == 12


def test_editor_mark_ignores_the_environment(configured: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del configured
    monkeypatch.setenv("NIX_UI__EDITOR_CALLED", "false")
    monkeypatch.setenv("NIX_UI__THEME", "paper")
    clear_config_cache()
    env = env_overrides()
    assert env.get("ui") == {"theme": "paper"}

    mark_editor_called(source="mcp")
    clear_config_cache()
    assert load_config().ui.editor_called is True

    monkeypatch.setenv("NIX_UI__EDITOR_CALLED", "true")
    _write_mark(False)
    assert load_config().ui.editor_called is False
    assert "editor_called" not in env_overrides().get("ui", {})


def test_status_stays_up_when_the_editor_mark_cannot_be_saved(
    client: WebClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _search_call()
    assert load_config().ui.editor_called is False

    def _broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("não foi possível gravar a marca")

    monkeypatch.setattr("nix.web.routes.ops.mark_editor_called", _broken)
    _open(client)
    assert load_config().ui.editor_called is False


def _step_row(html: str, title: str) -> str:
    marker = f"<strong>{title}</strong>"
    at = html.find(marker)
    if at < 0:
        raise AssertionError(f"O Status não mostrou o passo {title}.")
    start = html.rfind('<div class="list-row">', 0, at)
    end = html.find("</div>", at)
    if start < 0 or end < 0:
        raise AssertionError(f"O passo {title} não está numa linha do caminho inicial.")
    return html[start:end]


def _write_mark(value: bool) -> None:
    SettingsStore().write_many([("ui", "editor_called", value)], source="test", record_history=False)
    clear_config_cache()


def _mark_history_rows() -> int:
    with SettingsStore().transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM settings_history WHERE section = ? AND key = ?",
            ("ui", "editor_called"),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _insert_mark_history() -> int:
    with SettingsStore().transaction() as conn:
        conn.execute(
            """
            INSERT INTO settings_history (section, key, old_value_json, new_value_json, source, changed_at)
            VALUES ('ui', 'editor_called', NULL, 'true', 'mcp', '2026-01-01T00:00:00+00:00')
            """
        )
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
    assert row is not None
    return int(row[0])


def _cli_text(result: Any) -> str:
    stderr = getattr(result, "stderr", "") or ""
    return f"{result.output}{stderr}"
