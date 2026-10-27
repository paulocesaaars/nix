"""Sincronização em segundo plano e uma trava de leitura por vault."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from nix.core.errors import NixError
from nix.core.index.lock import mark_sync_job, unmark_sync_job
from nix.core.index.sync import combine_sync_reports
from nix.core.models import SyncProgress, SyncReport
from nix.core.runtime import Runtime, RuntimeHost, VaultSpec
from nix.observability.logging import get_logger

logger = get_logger("nix.web")

SyncItem = SyncProgress | SyncReport | NixError


@dataclass(frozen=True)
class BorrowedVaults:
    """Runtimes com a trava do vault segurada. `skipped` é quem estava sincronizando."""

    runtimes: list[Runtime]
    skipped: list[dict[str, str]]
    notice: str | None
    error: str | None = None


class RuntimeGate:
    """Uma trava por vault, para ler um enquanto outro sincroniza.

    A conexão SQLite de cada runtime não é compartilhada entre threads.
    """

    def __init__(self, host: RuntimeHost) -> None:
        self.host = host
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._refresh = threading.Lock()

    def lock_for(self, name: str) -> threading.Lock:
        key = name.strip().casefold()
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def try_before_call(self) -> tuple[bool, str | None]:
        """Recarrega a configuração se ninguém mais estiver fazendo isso."""
        if not self._refresh.acquire(blocking=False):
            return False, self.host.restart_notice
        try:
            return True, self.host.before_call()
        finally:
            self._refresh.release()

    def before_call(self) -> str | None:
        ran, notice = self.try_before_call()
        if ran:
            return notice
        return self.host.restart_notice

    @contextmanager
    def borrow(self, spec: VaultSpec) -> Iterator[BorrowedVaults]:
        """Segura a trava dos vaults livres. Quem está em sync entra em `skipped`."""
        notice = self.before_call()
        locks: list[threading.Lock] = []
        try:
            try:
                selected = self.host.vaults_for(spec)
            except NixError as exc:
                yield BorrowedVaults([], [], notice, exc.message)
                return
            selected = sorted(selected, key=lambda vault: vault.name.casefold())
            runtimes: list[Runtime] = []
            skipped: list[dict[str, str]] = []
            for vault in selected:
                lock = self.lock_for(vault.name)
                if not lock.acquire(blocking=False):
                    skipped.append({"vault": vault.name, "message": vault_busy_message(vault.name)})
                    continue
                locks.append(lock)
                try:
                    runtimes.append(self.host.resolve(vault.name))
                except NixError as exc:
                    skipped.append({"vault": vault.name, "message": exc.message})
                    lock.release()
                    locks.pop()
            yield BorrowedVaults(runtimes, skipped, notice, None)
        finally:
            for lock in locks:
                lock.release()


def vault_busy_message(name: str) -> str:
    return (
        f"O índice do vault {name} está em uso por uma sincronização. "
        "Espere ela terminar e atualize a página."
    )


class SyncRun:
    """Fila de progresso lida pelo SSE. Os eventos ficam no processo até o fim."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_done: Callable[[], None]) -> None:
        self._loop = loop
        self._on_done = on_done
        self._wake = asyncio.Event()
        self.events: list[SyncItem] = []
        self.finished = False
        self.selected_vault = ""
        self.all_vaults = False

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


def launch_sync(jobs: SyncJobs, gate: RuntimeGate, run: SyncRun, *, full: bool, spec: VaultSpec) -> None:
    """Dispara o sync numa thread, um vault por vez. O progresso cita o vault atual."""

    def worker() -> None:
        outcome: SyncReport | NixError | None = None
        reports: list[tuple[str, SyncReport]] = []
        try:
            try:
                gate.before_call()
                selected = gate.host.vaults_for(spec)
            except NixError as exc:
                outcome = exc
                selected = []
            for vault in selected:
                lock = gate.lock_for(vault.name)
                lock.acquire()
                try:
                    mark_sync_job(vault.name)
                    gate.host.before_call()
                    runtime = gate.host.resolve(vault.name)
                    report = runtime.indexer.sync(full=full, progress=run.add, trigger="manual")
                    report.vault_name = vault.name
                    reports.append((vault.name, report))
                except NixError as exc:
                    reports.append((vault.name, SyncReport(failed=1, errors=[exc.message])))
                except Exception:
                    logger.exception("Falha ao sincronizar o vault %s pela interface.", vault.name)
                    reports.append(
                        (
                            vault.name,
                            SyncReport(
                                failed=1,
                                errors=[
                                    f"A sincronização do vault {vault.name} falhou. "
                                    "Rode `nix doctor` e tente de novo."
                                ],
                            ),
                        )
                    )
                finally:
                    unmark_sync_job(vault.name)
                    lock.release()
            if outcome is None:
                if not reports:
                    outcome = NixError(
                        "Nenhum vault foi sincronizado. Cadastre um com `nix vault add` ou rode `nix init`."
                    )
                else:
                    outcome = combine_sync_reports(reports)
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
