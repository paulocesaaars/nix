"""Cenários de `bdd/` sobre escrita pelas ferramentas: HU-05, HU-06 e HU-11."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.conftest import SECOND_VAULT_NAME

from nix.core.errors import ConfigError, ConfirmationRequiredError, PathEscapeError
from nix.core.runtime import RuntimeHost
from nix.core.tools.registry import call_tool, register_tools


def _markdowns(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*.md")}


class _ToolServer:
    """Servidor MCP falso: guarda os kwargs de cada ferramenta registrada."""

    def __init__(self) -> None:
        self.registered: list[dict[str, object]] = []

    def tool(self, **kwargs: object) -> Callable[[Callable[..., object]], Callable[..., object]]:
        self.registered.append(kwargs)

        def decorator(fn: Callable[..., object]) -> Callable[..., object]:
            return fn

        return decorator


@pytest.mark.bdd("HU-05.1")
def test_created_note_is_searchable_without_manual_sync(configured: Path, host: RuntimeHost) -> None:
    del configured
    created = call_tool(
        host,
        "create_note",
        {
            "rel_path": "Inbox/farol.md",
            "content": "# Farol\n\nO farol de quinino fica na margem.\n",
        },
    )

    assert isinstance(created, dict)
    assert created["indexed"] is True
    found = call_tool(host, "search_notes", {"query": "farol de quinino"})
    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list)
    assert any(
        isinstance(row, dict) and row["rel_path"] == "Inbox/farol.md" and "quinino" in str(row["content"])
        for row in results
    )


@pytest.mark.bdd("HU-05.2")
def test_replace_without_confirm_does_not_write(configured: Path, host: RuntimeHost) -> None:
    note = configured / "Inbox" / "reuniao.md"
    before = note.read_text(encoding="utf-8")

    with pytest.raises(ConfirmationRequiredError, match="confirm=true"):
        call_tool(
            host,
            "update_note",
            {"rel_path": "Inbox/reuniao.md", "content": "não deve gravar", "mode": "replace"},
        )

    assert note.read_text(encoding="utf-8") == before


@pytest.mark.bdd("HU-05.3")
def test_write_outside_the_vault_is_rejected(configured: Path, host: RuntimeHost, tmp_path: Path) -> None:
    escaped = tmp_path / "fora.md"
    absolute = tmp_path / "absoluto.md"
    before = _markdowns(configured)

    with pytest.raises(PathEscapeError):
        call_tool(host, "create_note", {"rel_path": "../fora.md", "content": "fora"})
    with pytest.raises(PathEscapeError):
        call_tool(
            host,
            "create_note",
            {"rel_path": absolute.resolve().as_posix(), "content": "absoluto"},
        )

    assert not escaped.exists()
    assert not absolute.exists()
    assert _markdowns(configured) == before


@pytest.mark.bdd("HU-06.4")
def test_note_update_is_reindexed_in_the_same_operation(configured: Path, host: RuntimeHost) -> None:
    del configured
    call_tool(host, "sync_index", {})
    updated = call_tool(
        host,
        "update_note",
        {
            "rel_path": "Inbox/reuniao.md",
            "content": "# Reunião\n\nA senha do cofre é violeta-nix.\n",
            "mode": "replace",
            "confirm": True,
        },
    )

    assert isinstance(updated, dict)
    assert updated["indexed"] is True
    found = call_tool(host, "search_notes", {"query": "violeta-nix"})
    assert isinstance(found, dict)
    results = found["results"]
    assert isinstance(results, list)
    assert any(
        isinstance(row, dict) and row["rel_path"] == "Inbox/reuniao.md" and "violeta-nix" in str(row["content"])
        for row in results
    )


@pytest.mark.bdd("HU-06.5")
def test_destructive_writes_require_confirm_and_declare_hint(configured: Path, host: RuntimeHost) -> None:
    server = _ToolServer()
    register_tools(server, host)
    for name in ("update_note", "delete_note"):
        found = next(item for item in server.registered if item["name"] == name)
        annotations = found["annotations"]
        assert isinstance(annotations, BaseModel)
        assert annotations.model_dump(by_alias=True)["destructiveHint"] is True

    meeting = configured / "Inbox" / "reuniao.md"
    diary = configured / "Diario" / "2026-10-28.md"
    meeting_before = meeting.read_text(encoding="utf-8")
    diary_before = diary.read_text(encoding="utf-8")

    with pytest.raises(ConfirmationRequiredError, match="confirm=true"):
        call_tool(
            host,
            "update_note",
            {"rel_path": "Inbox/reuniao.md", "content": "não deve gravar", "mode": "replace"},
        )
    with pytest.raises(ConfirmationRequiredError, match="confirm=true"):
        call_tool(host, "delete_note", {"rel_path": "Diario/2026-10-28.md"})
    assert meeting.read_text(encoding="utf-8") == meeting_before
    assert diary.read_text(encoding="utf-8") == diary_before

    replaced = call_tool(
        host,
        "update_note",
        {
            "rel_path": "Inbox/reuniao.md",
            "content": "# Reunião\n\nTexto confirmado.\n",
            "mode": "replace",
            "confirm": True,
        },
    )
    deleted = call_tool(host, "delete_note", {"rel_path": "Diario/2026-10-28.md", "confirm": True})

    assert isinstance(replaced, dict) and replaced["action"] == "updated"
    assert "Texto confirmado." in meeting.read_text(encoding="utf-8")
    assert isinstance(deleted, dict) and deleted["action"] == "deleted"
    assert not diary.exists()


@pytest.mark.bdd("HU-11.1")
def test_write_rejects_vault_list_and_star(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    host = second_registered
    before_default = _markdowns(configured)
    before_second = _markdowns(second_vault)
    payloads = (
        {"vault": ["Default", SECOND_VAULT_NAME], "rel_path": "nao-grava.md", "content": "não gravar"},
        {"vault": "*", "rel_path": "nao-grava.md", "content": "não gravar"},
    )

    for payload in payloads:
        with pytest.raises(ConfigError, match="um nome só") as caught:
            call_tool(host, "create_note", payload)
        assert "omita para usar o padrão" in caught.value.message

    assert _markdowns(configured) == before_default
    assert _markdowns(second_vault) == before_second


@pytest.mark.bdd("HU-11.2")
def test_write_with_one_name_stays_in_that_vault(
    configured: Path,
    second_vault: Path,
    second_registered: RuntimeHost,
) -> None:
    host = second_registered
    created = call_tool(
        host,
        "create_note",
        {"vault": SECOND_VAULT_NAME, "rel_path": "Inbox/so-neste.md", "content": "Texto só neste vault.\n"},
    )

    assert isinstance(created, dict)
    assert created["vault"] == SECOND_VAULT_NAME
    assert created["rel_path"] == "Inbox/so-neste.md"
    written = (second_vault / "Inbox" / "so-neste.md").read_text(encoding="utf-8")
    assert "Texto só neste vault." in written
    assert not (configured / "Inbox" / "so-neste.md").exists()
