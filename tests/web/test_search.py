"""Cenário de `bdd/` da busca na interface: HU-08.8."""

from __future__ import annotations

import re

import pytest
from tests.web.conftest import WebClient

from nix.core.tools.registry import call_tool

_QUERY = "CEP"
_TOP_K = 8
_SCORE = re.compile(r"score ([0-9]+(?:\.[0-9]+)?)")
_LINES = re.compile(r"linhas (\d+)–(\d+)")
_WORD = re.compile(r"\w{4,}")
_QUERY_WORD = re.compile(r"\w{3,}")


def _visible_token(content: str, query: str) -> str:
    """Palavra do trecho que o realce da consulta não parte no HTML."""
    terms = {word.lower() for word in _QUERY_WORD.findall(query)}
    for word in _WORD.findall(content[:700]):
        lower = word.lower()
        if any(term in lower for term in terms):
            continue
        return word
    raise AssertionError("O trecho não tem uma palavra estável fora da consulta para conferir na página.")


@pytest.mark.bdd("HU-08.8")
def test_search_page_matches_search_notes(client: WebClient) -> None:
    host = client.gate.host
    host.resolve(None).indexer.sync()
    vault = host.config.default_vault.name
    found = call_tool(
        host,
        "search_notes",
        {
            "query": _QUERY,
            "top_k": _TOP_K,
            "folder": None,
            "tags": None,
            "date_from": None,
            "date_to": None,
            "vault": [vault],
        },
    )
    results = found["results"]
    assert results, "A busca não devolveu trechos para comparar com a página."

    page = client.get("/search", params={"q": _QUERY, "top_k": str(_TOP_K)})
    assert page.status_code == 200
    html = page.text
    assert f"{len(results)} trecho" in html
    assert html.count('class="card hit"') == len(results)

    shown_scores = [float(item) for item in _SCORE.findall(html)]
    expected_scores = [float(hit["score"]) for hit in results]
    assert shown_scores == expected_scores

    shown_lines = _LINES.findall(html)
    expected_lines = [(str(hit["start_line"]), str(hit["end_line"])) for hit in results if hit["start_line"]]
    assert shown_lines == expected_lines

    for hit in results:
        assert hit["rel_path"] in html
        assert _visible_token(str(hit["content"]), _QUERY) in html
