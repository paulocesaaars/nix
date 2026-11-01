"""Decide o que entra no Mega Brain e grava a observação.

Consentimento: o Mega Brain está ligado e existe hook global daquele agente
ou hook do projeto. O `.nix.toml` pode desligar a captura ou excluir caminhos.
"""

from __future__ import annotations

from nix.core.brain.events import SessionEvent
from nix.core.brain.limits import load_brain_flags
from nix.core.brain.paths import match_glob
from nix.core.brain.project import resolve_project
from nix.core.brain.store import BrainStore


def record(event: SessionEvent, store: BrainStore | None = None) -> bool:
    """Grava o evento. Devolve False quando ele foi recusado."""
    if not load_brain_flags().enabled:
        return False
    project = resolve_project(event.cwd or event.project)
    if not project.capture_enabled:
        return False
    if _excluded(event.target, project.key, project.exclude):
        return False
    target = store or BrainStore()
    if not target.capture_allowed(project.key, event.agent):
        return False
    remembered = event if event.project == project.key else _with_project(event, project.key)
    target.record(remembered, project.name)
    return True


def _with_project(event: SessionEvent, project_key: str) -> SessionEvent:
    return SessionEvent(
        id=event.id,
        agent=event.agent,
        session_id=event.session_id,
        project=project_key,
        project_name=event.project_name,
        cwd=event.cwd,
        type=event.type,
        ts=event.ts,
        tool=event.tool,
        target=event.target,
        text=event.text,
        is_error=event.is_error,
    )


def _excluded(target: str, project_key: str, patterns: tuple[str, ...]) -> bool:
    if not target or not patterns:
        return False
    relative = _relative(target, project_key)
    raw = target.replace("\\", "/")
    return any(match_glob(relative, pattern) or match_glob(raw, pattern) for pattern in patterns)


def _relative(target: str, project_key: str) -> str:
    raw = target.replace("\\", "/").lstrip("./")
    root = project_key.replace("\\", "/").rstrip("/")
    if raw.lower().startswith(root.lower() + "/"):
        return raw[len(root) + 1 :]
    return raw
