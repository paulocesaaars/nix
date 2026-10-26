"""Trava entre processos para sync e write-through.

O sistema operacional solta a trava se o processo morrer, então não há
arquivo de dono para limpar à mão.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import BinaryIO

from nix.config.paths import default_state_dir
from nix.core.errors import IndexBusyError
from nix.observability.logging import get_logger

logger = get_logger("nix.index.lock")

_TIMEOUT_S = 30 * 60
_POLL_S = 0.25


@contextmanager
def index_lock() -> Iterator[None]:
    directory = default_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sync.lock"
    handle = path.open("a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        _acquire(handle, str(path))
        try:
            yield
        finally:
            _release(handle)
    finally:
        handle.close()


def _busy() -> IndexBusyError:
    return IndexBusyError(
        "Outro processo do Nix está sincronizando o índice. Espere ele terminar e tente de novo."
    )


def _acquire(handle: BinaryIO, label: str) -> None:
    if sys.platform == "win32":
        import msvcrt

        def attempt() -> None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

        _spin(label, attempt)
        return

    import fcntl

    def attempt_unix() -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    _spin(label, attempt_unix)


def _spin(label: str, attempt: Callable[[], None]) -> None:
    deadline = time.monotonic() + _TIMEOUT_S
    announced = False
    while True:
        try:
            attempt()
            return
        except OSError:
            if not announced:
                logger.info("À espera da trava de sincronização em %s", label)
                announced = True
            if time.monotonic() >= deadline:
                raise _busy() from None
            time.sleep(_POLL_S)


def _release(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        with suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
