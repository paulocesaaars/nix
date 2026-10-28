"""Cenários de `bdd/` dos botões durante a sincronização: HU-14.1 a HU-14.4."""

from __future__ import annotations

import re
import threading
import time

import pytest
from tests.web.conftest import WebClient

from nix.web.jobs import SyncJobs
from nix.web.state import WebState

_CONTROLS = re.compile(r'<fieldset id="sync-controls"[^>]*>')
_LABELS = ("Prévia", "Incremental", "Reindexação completa", "Todos os vaults")
_WAIT = "Espere ela terminar"


def _jobs(client: WebClient) -> SyncJobs:
    state = client.app.state.web
    if not isinstance(state, WebState):
        raise AssertionError("O cliente de teste não tem o estado da interface.")
    return state.jobs


def _controls_disabled(html: str) -> bool:
    match = _CONTROLS.search(html)
    if match is None:
        raise AssertionError("A página não trouxe o fieldset #sync-controls.")
    return "disabled" in match.group(0)


def _assert_labels(html: str) -> None:
    for label in _LABELS:
        assert label in html


def _assert_no_scan(html: str) -> None:
    """O 409 avisa a espera e não traz o relatório da prévia."""
    assert "adicionados" not in html
    assert "nada foi gravado" not in html


def _wait_until_enabled(client: WebClient) -> str:
    """Recarrega até o job soltar os controles. Cada GET gira o loop que encerra o job."""
    deadline = time.monotonic() + 20
    last = ""
    while time.monotonic() < deadline:
        page = client.get("/sync")
        assert page.status_code == 200
        last = page.text
        if not _controls_disabled(last):
            return last
        time.sleep(0.05)
    raise AssertionError("Os controles não voltaram depois que a sincronização terminou.")


@pytest.mark.bdd("HU-14.1")
def test_sync_start_disables_controls(client: WebClient, embed_hold: threading.Event) -> None:
    try:
        started = client.post_csrf("/sync/start")
        assert started.status_code == 200
        assert _jobs(client).running()
        assert _controls_disabled(started.text)
        assert "em andamento" in started.text
        _assert_labels(started.text)
    finally:
        embed_hold.set()


@pytest.mark.bdd("HU-14.2")
def test_sync_page_stays_disabled_while_job_runs(client: WebClient, embed_hold: threading.Event) -> None:
    try:
        started = client.post_csrf("/sync/start")
        assert started.status_code == 200
        assert _jobs(client).running()

        reloaded = client.get("/sync")
        assert reloaded.status_code == 200
        assert _jobs(client).running()
        assert _controls_disabled(reloaded.text)
        _assert_labels(reloaded.text)
    finally:
        embed_hold.set()


@pytest.mark.bdd("HU-14.3")
def test_sync_controls_return_when_job_finishes(client: WebClient, embed_hold: threading.Event) -> None:
    try:
        started = client.post_csrf("/sync/start")
        assert started.status_code == 200
        assert _jobs(client).running()

        embed_hold.set()
        page = _wait_until_enabled(client)
        assert not _controls_disabled(page)
        _assert_labels(page)
        assert "Nenhuma sincronização registrada." not in page
        assert '<span class="badge b-n">manual</span>' in page
    finally:
        embed_hold.set()


@pytest.mark.bdd("HU-14.4")
def test_request_during_job_waits_without_scan(client: WebClient, embed_hold: threading.Event) -> None:
    try:
        started = client.post_csrf("/sync/start")
        assert started.status_code == 200
        assert _jobs(client).running()

        again = client.post_csrf("/sync/start")
        assert again.status_code == 409
        assert _WAIT in again.text
        _assert_no_scan(again.text)

        preview = client.post_csrf("/sync/preview")
        assert preview.status_code == 409
        assert _WAIT in preview.text
        assert "prévia" in preview.text
        _assert_no_scan(preview.text)

        page = client.get("/sync")
        assert page.status_code == 200
        assert _jobs(client).running()
        assert _controls_disabled(page.text)
        assert "em andamento" in page.text
    finally:
        embed_hold.set()
