"""Trava entre processos para sync e write-through.

O sistema operacional solta a trava se o processo morrer, então não há
arquivo de dono para limpar à mão.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import BinaryIO

from nix.config.paths import default_state_dir
from nix.core.errors import ConfigError, IndexBusyError
from nix.observability.logging import get_logger

logger = get_logger("nix.index.lock")

_TIMEOUT_S = 30 * 60
_POLL_S = 0.25

_guard = threading.Lock()
_holders: dict[str, int] = {}
_jobs: dict[str, int] = {}
_idle_listeners: list[Callable[[str], None]] = []


@contextmanager
def index_lock(wiki_name: str) -> Iterator[None]:
    """Trava `{app_root}/.nix/sync-{nome}.lock`. Cada wiki sincroniza sem bloquear os outros."""
    name = _wiki_label(wiki_name)
    directory = default_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"sync-{name}.lock"
    handle = path.open("a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        _acquire(handle, name, str(path))
        _hold(name)
        try:
            yield
        finally:
            try:
                _release(handle)
            finally:
                _unhold(name)
    finally:
        handle.close()


def sync_in_progress(wiki_name: str) -> bool:
    """True se este processo ou outro está sincronizando a wiki."""
    name = _wiki_label(wiki_name)
    key = name.casefold()
    with _guard:
        if _holders.get(key, 0) > 0 or _jobs.get(key, 0) > 0:
            return True
    return _other_process_holds(name)


def mark_sync_job(wiki_name: str) -> None:
    """Marca a wiki que o job da interface está sincronizando agora.

    Vale antes mesmo da trava de arquivo, para o runtime não fechar no meio.
    """
    key = _wiki_label(wiki_name).casefold()
    with _guard:
        _jobs[key] = _jobs.get(key, 0) + 1


def unmark_sync_job(wiki_name: str) -> None:
    """Solta a marca do job. Se nada mais segura a wiki, avisa quem espera fechar o runtime."""
    name = _wiki_label(wiki_name)
    key = name.casefold()
    notify = False
    with _guard:
        count = _jobs.get(key, 0)
        if count <= 1:
            _jobs.pop(key, None)
            notify = count == 1
        else:
            _jobs[key] = count - 1
    if notify:
        _notify_idle(name)


def add_sync_idle_listener(listener: Callable[[str], None]) -> None:
    """Chamado quando a trava de sync ou o job da interface solta a wiki."""
    with _guard:
        if listener not in _idle_listeners:
            _idle_listeners.append(listener)


def remove_sync_idle_listener(listener: Callable[[str], None]) -> None:
    with _guard:
        if listener in _idle_listeners:
            _idle_listeners.remove(listener)


def _wiki_label(wiki_name: str) -> str:
    name = wiki_name.strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ConfigError(
            "A trava de sincronização precisa do nome da wiki. "
            "Rode `nix wiki list` e tente de novo."
        )
    return name


def _hold(name: str) -> None:
    key = name.casefold()
    with _guard:
        _holders[key] = _holders.get(key, 0) + 1


def _unhold(name: str) -> None:
    key = name.casefold()
    notify = False
    with _guard:
        count = _holders.get(key, 0)
        if count == 1:
            _holders.pop(key, None)
            notify = True
        elif count > 1:
            _holders[key] = count - 1
    if notify:
        _notify_idle(name)


def _notify_idle(name: str) -> None:
    with _guard:
        listeners = list(_idle_listeners)
    for listener in listeners:
        try:
            listener(name)
        except Exception:
            logger.exception(
                "Falha ao avisar que a sincronização da wiki %s terminou. "
                "Feche e abra de novo o `nix ui` ou o cliente MCP se uma wiki removido continuar aberto.",
                name,
            )


def _other_process_holds(name: str) -> bool:
    """True se outro processo segura o arquivo de trava agora. Não cria o arquivo."""
    path = default_state_dir() / f"sync-{name}.lock"
    if not path.is_file():
        return False
    try:
        handle = path.open("a+b")
    except OSError:
        return True
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            return False
        handle.seek(0)
        try:
            _try_lock(handle)
        except OSError:
            return True
        _release(handle)
        return False
    finally:
        handle.close()


def _busy(wiki_name: str) -> IndexBusyError:
    return IndexBusyError(
        f"Outro processo do Nix está sincronizando o índice da wiki {wiki_name}. "
        "Espere ele terminar e tente de novo."
    )


def _try_lock(handle: BinaryIO) -> None:
    """Uma tentativa, sem espera. OSError se a trava já está presa."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _acquire(handle: BinaryIO, wiki_name: str, label: str) -> None:
    def attempt() -> None:
        _try_lock(handle)

    _spin(wiki_name, label, attempt)


def _spin(wiki_name: str, label: str, attempt: Callable[[], None]) -> None:
    deadline = time.monotonic() + _TIMEOUT_S
    announced = False
    while True:
        try:
            attempt()
            return
        except OSError:
            if not announced:
                logger.info("À espera da trava de sincronização da wiki %s em %s", wiki_name, label)
                announced = True
            if time.monotonic() >= deadline:
                raise _busy(wiki_name) from None
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
