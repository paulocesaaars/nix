"""URI de leitura do SQLite sem `Path.as_uri` (que importa `urllib.request`, ~30 ms)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

_SLUG_BAD = re.compile(r"[^A-Za-z0-9._ -]+")


def readonly_uri(path: Path) -> str:
    posix = path.resolve().as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return f"file://{quote(posix, safe='/:')}?mode=ro"


def note_rel_path(folder: str, project_name: str, started: str, agent: str, short_id: str) -> str:
    """`{folder}/<projeto>/<AAAA-MM-DD>-<agente>-<id curto>.md` (RF-100)."""
    project = _SLUG_BAD.sub("-", project_name).strip(" .-") or "projeto"
    day = started[:10] if re.match(r"\d{4}-\d{2}-\d{2}", started) else "sem-data"
    return f"{folder.strip('/')}/{project}/{day}-{agent}-{short_id}.md"
