"""Histórico do Codex: `~/.codex/sessions/rollout-*.jsonl` e `archived_sessions`.

A pasta não é por projeto. Fica o arquivo mais novo que cita o caminho do
projeto. Sem essa ocorrência, não há como saber se a sessão é deste repositório.
"""

from __future__ import annotations

from pathlib import Path


def find_codex_history(project: Path) -> Path | None:
    root = Path.home() / ".codex"
    files: list[Path] = []
    for name in ("sessions", "archived_sessions"):
        folder = root / name
        if folder.is_dir():
            files.extend(path for path in folder.glob("rollout-*.jsonl") if path.is_file())
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    needles = _needles(project)
    for path in files[:30]:
        if _mentions(path, needles):
            return path
    return None


def _needles(project: Path) -> tuple[str, ...]:
    try:
        resolved = str(project.resolve())
    except OSError:
        resolved = str(project)
    posix = resolved.replace("\\", "/")
    return tuple(dict.fromkeys(item for item in (resolved, posix) if item))


def _mentions(path: Path, needles: tuple[str, ...]) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            chunk = handle.read(1024 * 1024)
    except OSError:
        return False
    return any(needle in chunk for needle in needles)
