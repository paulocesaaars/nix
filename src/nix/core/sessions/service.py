"""Operações de sessão que mais de uma interface usa: gravar a nota e consolidar a fila.

CLI, ferramentas MCP e interface local só delegam a este módulo (TDD §1, princípio 1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from nix.config.schema import NixConfig
from nix.core.errors import NixError
from nix.core.runtime import RuntimeHost
from nix.core.sessions import drain
from nix.core.sessions.render import render_session
from nix.core.sessions.store import SessionStore

log = logging.getLogger("nix.sessions.drain")


def write_note(host: RuntimeHost, store: SessionStore, session_key: str) -> tuple[str | None, str | None]:
    """Grava ou atualiza a nota da sessão no vault (RF-103). Devolve `(caminho, erro)`."""
    session = store.find_session(session_key)
    if session is None:
        return None, f"Sessão {session_key} não encontrada em sessions.db."
    cfg = host.config.sessions
    try:
        runtime = host.resolve(cfg.vault or None)
        result = render_session(runtime, store, session, folder=cfg.folder, max_bytes=cfg.max_note_bytes)
    except NixError as exc:
        return None, exc.message
    return result.rel_path, None


def consolidate(load_config: Callable[[], NixConfig], open_host: Callable[[], RuntimeHost]) -> None:
    """Consolidador do `session-end` (RF-136): um por vez, com um só modelo para a fila inteira.

    Roda num processo destacado: qualquer erro vai só para o log.
    """
    with drain.try_drain_lock() as held:
        if not held:
            return
        try:
            config = load_config()
            if not config.sessions.enabled:
                return
            store = SessionStore()
            host = open_host()
            try:
                while True:
                    keys = drain.pop_all()
                    if not keys:
                        break
                    for key in keys:
                        _, error = write_note(host, store, key)
                        if error:
                            log.warning("Nota da sessão %s não gravada: %s", key, error)
            finally:
                host.close()
            store.purge(config.sessions.retention_days)
        except Exception:  # noqa: BLE001 - processo destacado: o erro só vai para o log
            log.exception("Falha ao consolidar as notas de sessão.")
