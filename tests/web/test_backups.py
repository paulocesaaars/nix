"""Cenário de `bdd/` da restauração de backup na interface: HU-08.10."""

from __future__ import annotations

import pytest
from tests.web.conftest import WebClient

_REL = "Inbox/reuniao.md"
_STAMP = "20260115T120000"
_MODIFIED = "# Reunião\n\nTexto provisório antes da restauração.\n"
_RESTORED = "Decidimos validar CEP no cadastro."


@pytest.mark.bdd("HU-08.10")
def test_restore_backup_reverts_note_and_updates_index(client: WebClient) -> None:
    host = client.gate.host
    vault = host.config.default_vault
    note = vault.root / _REL
    original = note.read_text(encoding="utf-8")
    assert _RESTORED in original

    backup = host.config.vault_backup_dir(vault) / _STAMP / _REL
    backup.parent.mkdir(parents=True)
    backup.write_text(original, encoding="utf-8")
    note.write_text(_MODIFIED, encoding="utf-8")
    previous = note.read_text(encoding="utf-8")

    restored = client.post_csrf(
        "/backups/restore",
        data={"stamp": _STAMP, "path": _REL, "confirm": "on"},
    )
    assert restored.status_code == 200
    assert "Índice atualizado." in restored.text
    assert note.read_text(encoding="utf-8") == original

    copies = [path.read_text(encoding="utf-8") for path in host.config.vault_backup_dir(vault).rglob("*.md")]
    assert previous in copies

    page = client.get("/search", params={"q": "cadastro", "top_k": "8"})
    assert page.status_code == 200
    assert "Nenhum trecho encontrado" not in page.text
    assert _REL in page.text
    assert "Decidimos" in page.text
    assert "provisório" not in page.text
