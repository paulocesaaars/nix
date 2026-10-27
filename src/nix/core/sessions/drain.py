"""Fila de notas a renderizar e o processo destacado do `session-end` (RF-136).

O hook só enfileira a sessão e dispara `nix session render --drain` sem esperar.
Um único consolidador roda por vez na máquina (trava em arquivo): quem chega com
outro ativo sai, e o ativo processa a fila inteira com um só modelo de embedding.
Só a biblioteca padrão: o hook importa este módulo.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from nix.config.paths import app_root, default_state_dir, is_packaged


def queue_path() -> Path:
    return default_state_dir() / "sessions-render.queue"


def lock_path() -> Path:
    return default_state_dir() / "sessions-drain.lock"


def enqueue(session_key: str) -> None:
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(session_key.replace("\n", " ") + "\n")


def pop_all() -> list[str]:
    """Esvazia a fila de forma atômica e devolve as sessões, sem repetição, na ordem de chegada."""
    path = queue_path()
    taken = path.with_suffix(".taking")
    # Sobra de um consolidador que morreu no meio: entra de novo, senão o `replace` abaixo a apagaria.
    lines = _read_lines(taken)
    try:
        os.replace(path, taken)
    except FileNotFoundError:
        pass
    except OSError as exc:
        import logging

        logging.getLogger("nix.sessions.drain").warning(
            "Não foi possível tomar a fila %s: %s. As sessões seguem na fila para a próxima rodada.", path, exc
        )
    else:
        lines += _read_lines(taken)
    with contextlib.suppress(OSError):
        taken.unlink()
    seen: dict[str, None] = {}
    for line in lines:
        key = line.strip()
        if key:
            seen.setdefault(key, None)
    return list(seen)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def spawn_drain() -> None:
    """Dispara o consolidador em segundo plano e volta na hora."""
    base = [str(Path(sys.argv[0]).resolve())] if is_packaged() else [sys.executable, "-P", "-m", "nix"]
    command = [*base, "session", "render", "--drain"]
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "cwd": str(app_root()),
    }
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)  # type: ignore[call-overload]  # noqa: S603


@contextmanager
def try_drain_lock() -> Iterator[bool]:
    """`True` se este processo é o consolidador. O sistema solta a trava se o processo morrer."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    held = False
    try:
        held = _try_lock(handle)
        yield held
    finally:
        if held:
            _unlock(handle)
        handle.close()


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    with contextlib.suppress(OSError):
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
