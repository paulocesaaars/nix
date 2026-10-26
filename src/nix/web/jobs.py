"""Sincronização em segundo plano e exclusão do runtime do processo."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable

from nix.core.errors import NixError
from nix.core.models import SyncProgress, SyncReport
from nix.core.runtime import RuntimeHost
from nix.observability.logging import get_logger

logger = get_logger("nix.web")

SyncItem = SyncProgress | SyncReport | NixError


class RuntimeGate:
    """Serializa o uso do runtime. A conexão SQLite não é compartilhada entre threads."""

    def __init__(self, host: RuntimeHost) -> None:
        self.host = host
        self.lock = threading.Lock()

    def try_before_call(self) -> tuple[bool, str | None]:
        """Chama `before_call` se o runtime estiver livre. O primeiro valor diz se rodou."""
        if not self.lock.acquire(blocking=False):
            return False, None
        try:
            return True, self.host.before_call()
        finally:
            self.lock.release()


class SyncRun:
    """Fila de progresso lida pelo SSE. Os eventos ficam no processo até o fim."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_done: Callable[[], None]) -> None:
        self._loop = loop
        self._on_done = on_done
        self._wake = asyncio.Event()
        self.events: list[SyncItem] = []
        self.finished = False

    def add(self, event: SyncProgress) -> None:
        def _append() -> None:
            if self.finished:
                return
            self.events.append(event)
            self._wake.set()

        try:
            self._loop.call_soon_threadsafe(_append)
        except RuntimeError:
            return

    def finish(self, item: SyncReport | NixError) -> None:
        def _close() -> None:
            if self.finished:
                return
            self.events.append(item)
            self.finished = True
            self._wake.set()
            self._on_done()

        try:
            self._loop.call_soon_threadsafe(_close)
        except RuntimeError:
            return

    async def iter_items(self) -> AsyncIterator[SyncItem]:
        index = 0
        while True:
            if index < len(self.events):
                item = self.events[index]
                index += 1
                yield item
                if not isinstance(item, SyncProgress):
                    return
                continue
            if self.finished:
                return
            self._wake.clear()
            if index < len(self.events) or self.finished:
                continue
            await self._wake.wait()


class SyncJobs:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._run: SyncRun | None = None
        self._busy = False
        self._thread: threading.Thread | None = None

    def current(self) -> SyncRun | None:
        with self._guard:
            return self._run

    def running(self) -> bool:
        with self._guard:
            return self._busy

    def begin(self, loop: asyncio.AbstractEventLoop) -> SyncRun | None:
        with self._guard:
            if self._busy:
                return None
            run = SyncRun(loop, self._release)
            self._run = run
            self._busy = True
            return run

    def _release(self) -> None:
        with self._guard:
            self._busy = False

    def track(self, thread: threading.Thread) -> None:
        with self._guard:
            self._thread = thread

    def wait(self) -> None:
        """Espera a sincronização soltar o runtime antes de fechar o processo."""
        with self._guard:
            thread = self._thread
        if thread is not None:
            thread.join()


def launch_sync(jobs: SyncJobs, gate: RuntimeGate, run: SyncRun, *, full: bool) -> None:
    """Dispara `indexer.sync` numa thread. O callback só enfileira progresso."""

    def worker() -> None:
        outcome: SyncReport | NixError | None = None
        try:
            try:
                with gate.lock:
                    gate.host.before_call()
                    outcome = gate.host.runtime.indexer.sync(full=full, progress=run.add, trigger="manual")
            except NixError as exc:
                outcome = exc
            except Exception:
                logger.exception("Falha ao sincronizar pela interface.")
                outcome = NixError("A sincronização falhou. Rode `nix doctor` e tente de novo.")
        finally:
            if outcome is None:
                outcome = NixError("A sincronização foi interrompida. Rode `nix sync` de novo.")
            run.finish(outcome)

    thread = threading.Thread(target=worker, name="nix-ui-sync", daemon=False)
    jobs.track(thread)
    thread.start()
