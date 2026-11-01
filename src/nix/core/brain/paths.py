"""URI de leitura do SQLite e o glob de exclusão, sem puxar o pacote da wiki.

O hook importa este módulo. `match_glob` repete a regra de `nix.core.wiki.paths`
para o binário leve não seguir `core.wiki`.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from urllib.parse import quote

_SLUG_BAD = re.compile(r"[^A-Za-z0-9._ -]+")


def readonly_uri(path: Path) -> str:
    posix = path.resolve().as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return f"file://{quote(posix, safe='/:')}?mode=ro"


CURATED_DIRS: tuple[str, ...] = ("_rules", "decisions", "gotchas", "procedures", "concepts")
PROFILE_CATEGORIES: tuple[str, ...] = (
    "stack",
    "architecture",
    "workflow",
    "testing",
    "tools",
    "style",
    "habits",
)


def project_slug(name: str) -> str:
    """Segmento de pasta estável a partir do nome do projeto."""
    return _SLUG_BAD.sub("-", name).strip(" .-") or "projeto"


def session_page_rel(project_name: str, started: str, agent: str, short_id: str) -> str:
    """`projects/<projeto>/sessions/<AAAA-MM-DD>-<agente>-<id curto>.md`."""
    day = started[:10] if re.match(r"\d{4}-\d{2}-\d{2}", started) else "sem-data"
    safe_agent = _SLUG_BAD.sub("-", agent).strip(" .-") or "agente"
    safe_id = _SLUG_BAD.sub("", short_id)[:12] or "sessao"
    return f"projects/{project_slug(project_name)}/sessions/{day}-{safe_agent}-{safe_id}.md"


def match_glob(rel_posix: str, pattern: str) -> bool:
    """Glob estilo git, com suporte a `**`. Igual ao da wiki, de propósito."""
    pat = pattern.replace("\\", "/")
    if rel_posix == pat or fnmatch(rel_posix, pat):
        return True
    if pat.startswith("**/"):
        rest = pat[3:]
        if fnmatch(rel_posix, rest) or fnmatch(PurePosixPath(rel_posix).name, rest):
            return True
        parts = rel_posix.split("/")
        for index in range(len(parts)):
            if fnmatch("/".join(parts[index:]), rest):
                return True
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return rel_posix == prefix or rel_posix.startswith(prefix + "/")
    if "/**/" in pat:
        head, tail = pat.split("/**/", 1)
        if head and not rel_posix.startswith(head.rstrip("/") + "/") and rel_posix != head:
            return False
        return fnmatch(rel_posix, pat) or rel_posix.endswith("/" + tail) or fnmatch(PurePosixPath(rel_posix).name, tail)
    return False


def is_curated_or_profile(rel_path: str) -> bool:
    """Página que o agente pode gravar: curadoria do projeto ou perfil."""
    parts = rel_path.replace("\\", "/").strip("/").split("/")
    if len(parts) < 3 or not parts[-1] or parts[-1] in {".", ".."}:
        return False
    if parts[0] == "projects" and parts[2] in CURATED_DIRS:
        return True
    return parts[0] == "profile" and parts[1] in PROFILE_CATEGORIES
