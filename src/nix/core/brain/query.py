"""Busca do Mega Brain: a híbrida da wiki, filtrada, mais o FTS das observações."""

from __future__ import annotations

from nix.core.brain.paths import project_slug
from nix.core.brain.store import BrainStore
from nix.core.errors import ConfigError
from nix.core.retrieval.service import search_many
from nix.core.runtime import Runtime, RuntimeHost

_KIND_DIR = {
    "session": "sessions",
    "rule": "_rules",
    "decision": "decisions",
    "gotcha": "gotchas",
    "procedure": "procedures",
    "concept": "concepts",
}


def brain_query(
    host: RuntimeHost,
    *,
    query: str,
    project: str = "",
    scope: str = "project",
    path_prefix: str = "",
    tag: str = "",
    kind: str = "",
) -> dict[str, object]:
    text = query.strip()
    if not text:
        raise ConfigError("Informe o texto da busca em `query`.")
    if scope not in {"project", "global"}:
        raise ConfigError("scope deve ser `project` ou `global`.")
    wiki_name = _brain_wiki(host)
    runtime = host.resolve(wiki_name)
    store = BrainStore()
    project_key = ""
    folder = ""
    if scope == "project":
        project_key = _project_key(store, project)
        folder = f"projects/{project_slug(_project_name(store, project_key))}"
    prefix = path_prefix.strip().strip("/")
    tags = [tag.strip()] if tag.strip() else None
    found = search_many([(runtime.wiki.name, runtime.retrieval)], text, folder=folder or None, tags=tags)
    kind_dir = _kind_dir(kind)
    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for chunk in found.chunks:
        rel = chunk.rel_path.replace("\\", "/")
        if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
            continue
        if kind_dir and f"/{kind_dir}/" not in f"/{rel}":
            continue
        if rel in seen:
            continue
        seen.add(rel)
        pages.append({"path": rel, "title": chunk.title, "snippet": chunk.content[:400]})
    raw = store.search_observations(text, project_key or None)
    return {
        "wiki": runtime.wiki.name,
        "project": project_key,
        "scope": scope,
        "pages": pages,
        "raw_hits": raw,
        "wiki_errors": found.wiki_errors,
    }


def brain_runtime(host: RuntimeHost) -> Runtime:
    return host.resolve(_brain_wiki(host))


def _brain_wiki(host: RuntimeHost) -> str:
    name = host.config.brain.wiki.strip()
    if not name:
        raise ConfigError("O Mega Brain não tem wiki. Rode `nix brain enable --wiki NOME`.")
    return name


def _project_key(store: BrainStore, wanted: str) -> str:
    from nix.core.brain.events import find_project

    cleaned = wanted.strip()
    if not cleaned:
        return find_project("")[0]
    for item in store.list_projects():
        if cleaned == item.key or cleaned == item.name or cleaned.casefold() == item.name.casefold():
            return item.key
    return find_project(cleaned)[0]


def _project_name(store: BrainStore, project_key: str) -> str:
    for item in store.list_projects():
        if item.key == project_key:
            return item.name
    return project_key.rstrip("/").rsplit("/", 1)[-1] or "projeto"


def _kind_dir(kind: str) -> str:
    cleaned = kind.strip().lower()
    if not cleaned:
        return ""
    if cleaned not in _KIND_DIR:
        raise ConfigError(
            f"kind {kind!r} inválido. Use um de: {', '.join(_KIND_DIR)}, ou omita."
        )
    return _KIND_DIR[cleaned]
