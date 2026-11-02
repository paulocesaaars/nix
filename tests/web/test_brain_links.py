"""Links de conhecimento e perfil abrem a wiki do Mega Brain."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from tests.conftest import SECOND_WIKI_NAME
from tests.web.conftest import WebClient

from nix.config.editor import set_value
from nix.core.admin.wikis import DEFAULT_WIKI_NAME, WikiService
from nix.core.brain.events import SessionEvent, find_project
from nix.core.brain.store import BrainStore


def _remember(tmp_path: Path, name: str) -> str:
    folder = tmp_path / name
    folder.mkdir()
    (folder / ".git").mkdir()
    key, folder_name = find_project(str(folder))
    BrainStore().record(
        SessionEvent(
            id=f"evt-{name}",
            agent="claude",
            session_id=f"s-{name}",
            project=key,
            project_name=folder_name,
            cwd=str(folder),
            type="user-prompt",
            ts="2026-11-01T00:00:00+00:00",
            tool="",
            target="",
            text="pedido",
            is_error=False,
        ),
        folder_name,
    )
    return key


def _enable_brain_on_second_wiki(second_wiki: Path) -> None:
    WikiService().add(SECOND_WIKI_NAME, second_wiki)
    set_value("brain", "wiki", SECOND_WIKI_NAME, source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)


def _note_href(rel_path: str, wiki: str) -> str:
    return f"/notes/view?path={quote(rel_path)}&amp;wiki={quote(wiki)}"


def test_knowledge_link_opens_the_brain_wiki(client: WebClient, tmp_path: Path, second_wiki: Path) -> None:
    _enable_brain_on_second_wiki(second_wiki)
    key = _remember(tmp_path, "alfa")
    rel_path = "projects/alfa/sessions/2026-11-02-claude-nota.md"
    session = BrainStore().sessions_for(key)[0]
    BrainStore().set_page_path(session.key, rel_path)

    page = client.get(
        "/brain/project",
        params={"project": key, "tab": "conhecimento", "wiki": DEFAULT_WIKI_NAME},
    )

    assert page.status_code == 200
    assert _note_href(rel_path, SECOND_WIKI_NAME) in page.text
    assert _note_href(rel_path, DEFAULT_WIKI_NAME) not in page.text


def test_profile_link_opens_the_brain_wiki(client: WebClient, second_wiki: Path) -> None:
    _enable_brain_on_second_wiki(second_wiki)
    rel_path = "profile/tools/pnpm.md"
    BrainStore().upsert_profile(
        category="tools",
        sentence="usa pnpm",
        page_path=rel_path,
        evidence=[("alfa", "sempre pnpm")],
    )

    page = client.get("/brain/profile", params={"wiki": DEFAULT_WIKI_NAME})

    assert page.status_code == 200
    assert _note_href(rel_path, SECOND_WIKI_NAME) in page.text
    assert _note_href(rel_path, DEFAULT_WIKI_NAME) not in page.text
