"""Cenários de `bdd/` sobre busca e listas em vários vaults: HU-12."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests.conftest import SECOND_VAULT_NAME

from nix.config.loader import load_config
from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _sync_all(host: RuntimeHost) -> None:
    report = call_tool(host, "sync_index", {"vault": "*"})
    assert isinstance(report, dict)
    reports = report["reports"]
    assert isinstance(reports, list) and reports
    assert all(isinstance(item, dict) and "error" not in item for item in reports)


@pytest.mark.bdd("HU-12.1")
def test_search_star_returns_chunks_with_origin_vault(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    host = second_registered
    _write(configured, "Comum/sinal.md", "O sinal compartilhado é zxq-laranja.")
    _write(second_vault, "Comum/sinal.md", "O sinal compartilhado é zxq-laranja.")
    _sync_all(host)

    found = call_tool(host, "search_notes", {"query": "zxq-laranja", "vault": "*", "top_k": 10})

    assert isinstance(found, dict)
    assert found["vault_errors"] == []
    results = found["results"]
    assert isinstance(results, list) and results
    origins = {row["vault"] for row in results if isinstance(row, dict)}
    assert origins == {"Default", SECOND_VAULT_NAME}
    assert all(isinstance(row, dict) and row["vault"] for row in results)


@pytest.mark.bdd("HU-12.2")
def test_search_keeps_other_vaults_when_one_folder_is_gone(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    _write(second_vault, "Segredo/outro.md", "Segredo exclusivo do outro vault.")
    # O índice fica num host que é fechado antes de apagar a pasta. O host do
    # teste ainda não abriu esse vault, então a busca falha ao abrir e a falha
    # vai para vault_errors, sem derrubar os trechos do outro.
    indexer = RuntimeHost(load_config())
    try:
        _sync_all(indexer)
    finally:
        indexer.close()
    shutil.rmtree(second_vault)

    found = call_tool(second_registered, "search_notes", {"query": "ViaCEP", "vault": "*", "top_k": 10})

    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list) and results
    assert {row["vault"] for row in results if isinstance(row, dict)} == {"Default"}
    assert any(isinstance(row, dict) and "ViaCEP" in str(row["content"]) for row in results)
    errors = found["vault_errors"]
    assert isinstance(errors, list) and len(errors) == 1
    failure = errors[0]
    assert isinstance(failure, dict)
    assert failure["vault"] == SECOND_VAULT_NAME
    message = str(failure["message"])
    assert "não existe" in message
    assert "nix vault" in message
    leaked = [
        row
        for row in results
        if isinstance(row, dict) and "Segredo exclusivo do outro vault" in str(row.get("content"))
    ]
    assert leaked == []


@pytest.mark.bdd("HU-12.3")
def test_list_notes_limit_applies_per_vault(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    del configured
    host = second_registered
    _write(second_vault, "A/um.md", "Primeira nota do outro vault.")
    _write(second_vault, "B/dois.md", "Segunda nota do outro vault.")
    _sync_all(host)

    listed = call_tool(host, "list_notes", {"vault": "*", "limit": 1})

    assert isinstance(listed, dict)
    notes = listed["notes"]
    assert isinstance(notes, list)
    by_vault: dict[str, int] = {}
    for note in notes:
        assert isinstance(note, dict)
        name = str(note["vault"])
        by_vault[name] = by_vault.get(name, 0) + 1
    assert by_vault == {"Default": 1, SECOND_VAULT_NAME: 1}


@pytest.mark.bdd("HU-12.4")
def test_list_all_tags_sums_counts_then_applies_limit(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    # "comum" soma 3 e passa na frente de "alfa" (2 num vault só). O limite 1
    # entra depois dessa soma: se cortasse cada vault antes, "alfa" ganharia.
    _write(configured, "Tags/alfa-um.md", "---\ntags: [alfa]\n---\nNota alfa.\n")
    _write(configured, "Tags/alfa-dois.md", "---\ntags: [alfa]\n---\nOutra alfa.\n")
    _write(configured, "Tags/comum.md", "---\ntags: [comum]\n---\nNota comum.\n")
    _write(second_vault, "Tags/comum-a.md", "---\ntags: [comum]\n---\nComum no outro.\n")
    _write(second_vault, "Tags/comum-b.md", "---\ntags: [comum]\n---\nOutra comum.\n")
    _write(second_vault, "Tags/beta.md", "---\ntags: [beta]\n---\nNota beta.\n")
    _sync_all(second_registered)

    listed = call_tool(second_registered, "list_all_tags", {"vault": "*", "limit": 1})

    assert isinstance(listed, dict)
    tags = listed["tags"]
    assert isinstance(tags, list) and len(tags) == 1
    top = tags[0]
    assert isinstance(top, dict)
    assert top["tag"] == "comum"
    assert top["count"] == 3
    detail = {item["vault"]: item["count"] for item in top["vaults"] if isinstance(item, dict)}
    assert detail == {"Default": 1, SECOND_VAULT_NAME: 2}
