"""Cenários de `bdd/` da configuração na interface: HU-08.3, HU-08.4 e HU-08.5."""

from __future__ import annotations

import re

import pytest
from tests.web.conftest import WebClient

from nix.config.loader import clear_config_cache, load_config

_TOP_K = "retrieval.top_k"
_BADGE_DEFAULT = '<span class="badge b-n">padrão</span>'
_BADGE_DB = '<span class="badge b-a">settings.db</span>'
_INPUT = re.compile(r"<input\b[^>]*>", re.DOTALL)


def _field_block(html: str, dotted: str) -> str:
    """Trecho do formulário de um campo, do rótulo até o próximo."""
    marker = f"<strong>{dotted}</strong>"
    start = html.find(marker)
    if start < 0:
        raise AssertionError(f"A página não mostrou o campo {dotted}.")
    end = html.find("<strong>", start + len(marker))
    if end < 0:
        end = len(html)
    return html[start:end]


def _checked_fields(html: str) -> dict[str, str]:
    """Checkboxes marcados. Fora do POST, o formulário grava o booleano como desligado."""
    fields: dict[str, str] = {}
    for tag in _INPUT.findall(html):
        if 'type="checkbox"' not in tag or not re.search(r"\bchecked\b", tag):
            continue
        if re.search(r"\bdisabled\b", tag):
            continue
        name = re.search(r'name="([^"]+)"', tag)
        if name is not None:
            fields[name.group(1)] = "on"
    return fields


def _post_top_k(client: WebClient, page_html: str, value: str) -> str:
    data = _checked_fields(page_html)
    data[_TOP_K] = value
    saved = client.post_csrf("/settings", data=data)
    assert saved.status_code == 200
    assert "Configuração gravada." in saved.text
    assert 'class="alert alert-err"' not in saved.text
    return saved.text


def _change_id(html: str, dotted: str) -> int:
    needle = f'<td class="mono">{dotted}</td>'
    for row in html.split("<tr>")[1:]:
        if needle not in row:
            continue
        found = re.search(r'<td class="muted">(\d+)</td>', row)
        if found is not None:
            return int(found.group(1))
    raise AssertionError(f"O histórico não registrou {dotted}.")


@pytest.mark.bdd("HU-08.3")
def test_save_valid_field_replaces_default_origin(client: WebClient) -> None:
    before = client.get("/settings")
    assert before.status_code == 200
    original = _field_block(before.text, _TOP_K)
    assert _BADGE_DEFAULT in original
    assert 'value="5"' in original

    saved = _post_top_k(client, before.text, "12")
    block = _field_block(saved, _TOP_K)
    assert _BADGE_DB in block
    assert _BADGE_DEFAULT not in block
    assert 'value="12"' in block
    assert load_config().retrieval.top_k == 12


@pytest.mark.bdd("HU-08.4")
def test_env_field_stays_locked(client: WebClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIX_RETRIEVAL__TOP_K", "9")
    # O GET da sessão já carregou a config; sem limpar, a página ignora o ambiente.
    clear_config_cache()

    page = client.get("/settings")
    assert page.status_code == 200
    block = _field_block(page.text, _TOP_K)
    assert "ambiente · travado" in block
    assert "disabled" in block
    assert 'value="9"' in block
    assert _BADGE_DEFAULT not in block
    assert load_config().retrieval.top_k == 9


@pytest.mark.bdd("HU-08.5")
def test_undo_restores_previous_value(client: WebClient) -> None:
    before = client.get("/settings")
    assert before.status_code == 200
    _post_top_k(client, before.text, "12")
    assert load_config().retrieval.top_k == 12

    history = client.get("/history")
    assert history.status_code == 200
    change_id = _change_id(history.text, _TOP_K)

    undone = client.post_csrf(f"/history/{change_id}/undo")
    assert undone.status_code == 200
    assert f"Alteração #{change_id} desfeita." in undone.text

    assert load_config().retrieval.top_k == 5
    again = client.get("/settings")
    assert again.status_code == 200
    block = _field_block(again.text, _TOP_K)
    assert 'value="5"' in block
    assert _BADGE_DEFAULT in block
    assert _BADGE_DB not in block
