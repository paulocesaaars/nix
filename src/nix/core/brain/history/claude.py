"""Histórico do Claude Code: `~/.claude/projects/<projeto>/<sessão>.jsonl`.

O nome da pasta troca cada caractere que não é letra nem dígito por `-`.
`CLAUDE_CODE_PROJECT_DIR_NAME` só vale junto com `CLAUDE_CONFIG_DIR`.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_claude_history(project: Path) -> Path | None:
    config = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(config) if config else Path.home() / ".claude"
    custom = os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME", "").strip() if config else ""
    slug = custom or _slug(project)
    folder = base / "projects" / slug
    if not folder.is_dir():
        return None
    files = [path for path in folder.glob("*.jsonl") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _slug(project: Path) -> str:
    try:
        text = str(project.resolve())
    except OSError:
        text = str(project)
    return "".join(char if char.isalnum() else "-" for char in text)
