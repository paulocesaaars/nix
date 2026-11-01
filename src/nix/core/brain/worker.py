"""Trabalho em segundo plano: encerra sessões ociosas e grava a página na wiki.

O hook só chama `schedule`. O processo destacado (`nix brain work`) é que abre
o índice. Nos testes, `NIX_BRAIN_WORK_INLINE=1` grava na mesma chamada.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from typing import IO

from nix.config.executables import cli_to_launch
from nix.config.paths import default_state_dir
from nix.core.brain.limits import load_brain_flags
from nix.core.brain.pages import build_session_page, page_path_for
from nix.core.brain.store import BrainStore, SessionRecord

log = logging.getLogger("nix.brain.worker")


def schedule(session_key: str) -> None:
    """Pede a página. Inline nos testes; no uso normal, não espera o índice."""
    if os.environ.get("NIX_BRAIN_WORK_INLINE") == "1":
        run_work(session_key)
        return
    try:
        _spawn(session_key)
    except OSError as exc:
        _log_spawn(f"Não abri o processo da página ({exc}). Rode o instalador de novo.")


def run_work(session_key: str | None = None) -> None:
    """Grava as páginas das sessões encerradas que ainda não têm página."""
    del session_key
    with _work_lock() as acquired:
        if not acquired:
            return
        store = BrainStore()
        flags = load_brain_flags()
        store.close_idle(flags.idle_end_after_hours)
        pending = store.pending_pages()
        if not pending:
            return
        if not flags.wiki:
            log.warning("Mega Brain ligado sem wiki. Rode `nix brain enable --wiki NOME`.")
            return
        _write_pages(store, flags.wiki, pending)


def _write_pages(store: BrainStore, wiki_name: str, pending: list[SessionRecord]) -> None:
    from nix.config.loader import load_config
    from nix.core.errors import NixError
    from nix.core.runtime import RuntimeHost

    host = RuntimeHost(load_config(use_cache=False))
    try:
        runtime = host.resolve(wiki_name)
        for session in pending:
            from nix.core.brain.tokens import report

            observations = store.observations(session.key)
            body, frontmatter = build_session_page(
                session,
                observations,
                tokens_line=report(session.key, store),
            )
            rel = page_path_for(session)
            result = runtime.writer.create_note(rel, body, frontmatter, overwrite=True, confirm=True)
            runtime.writeback.after_write(result)
            store.set_page_path(session.key, result.rel_path)
    except NixError:
        log.warning("Falha ao gravar a página da sessão.", exc_info=True)
        raise
    finally:
        host.close()


def _spawn(session_key: str) -> None:
    """Abre o binário completo. O `nix-hook` só recebe eventos e não grava a página."""
    if _packaged():
        program = cli_to_launch(sys.argv[0] if sys.argv else "", sys.executable)
        if not program.is_file():
            name = "nix.exe" if sys.platform == "win32" else "nix"
            _log_spawn(
                f"Não achei o binário completo em {program}. "
                f"Confira se {name} está em NIX_HOME/bin e rode o instalador de novo."
            )
            return
        cmd = [str(program), "brain", "work", "--session", session_key]
    else:
        cmd = [sys.executable, "-m", "nix", "brain", "work", "--session", session_key]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def _packaged() -> bool:
    """True no binário Nuitka. `__compiled__` existe neste módulo compilado."""
    return "__compiled__" in globals() or getattr(sys, "frozen", False)


def _log_spawn(message: str) -> None:
    """Mesmo arquivo do hook, para a falha aparecer sem o agente aberto."""
    try:
        directory = default_state_dir() / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with (directory / "brain-hook.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        return


@contextmanager
def _work_lock() -> Iterator[bool]:
    path = default_state_dir() / "brain-work.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        try:
            _lock(handle)
            acquired = True
        except OSError:
            yield False
            return
        yield True
    finally:
        if acquired:
            _unlock(handle)
        handle.close()


def _lock(handle: IO[bytes]) -> None:
    fd = handle.fileno()
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: IO[bytes]) -> None:
    fd = handle.fileno()
    if sys.platform == "win32":
        import msvcrt

        with suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    with suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)
