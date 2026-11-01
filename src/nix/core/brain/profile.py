"""Perfil sem modelo de linguagem: listas de palavras, evidência e lápide.

A frase mais nova ganha. Uma entrada esquecida não volta na passada seguinte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nix.config.loader import load_config
from nix.core.brain.paths import PROFILE_CATEGORIES
from nix.core.brain.project import resolve_project
from nix.core.brain.store import BrainStore, ProfileRecord
from nix.core.errors import ConfigError, NoteNotFoundError

# Gatilhos em português e inglês. O termo seguinte vira o assunto da entrada.
_PREFERENCE = re.compile(
    r"(?i)\b(?:sempre use|sempre usar|always use|prefiro|eu prefiro|i prefer|nunca use|never use)\s+"
    r"([A-Za-z0-9][\w.+-]*)"
)
# Nomes que caem em profile/tools/. O restante vai para habits.
_TOOLS = frozenset(
    {
        "pnpm",
        "npm",
        "yarn",
        "bun",
        "pip",
        "uv",
        "cargo",
        "pytest",
        "ruff",
        "mypy",
        "docker",
        "git",
        "make",
    }
)


@dataclass(frozen=True)
class Preference:
    project_key: str
    project_name: str
    quote: str
    ts: str


def extract(text: str) -> list[tuple[str, str]]:
    """Pares (assunto, trecho) achados no pedido."""
    found: list[tuple[str, str]] = []
    for match in _PREFERENCE.finditer(text):
        found.append((match.group(1), match.group(0).strip()))
    return found


def rebuild(store: BrainStore | None = None) -> list[ProfileRecord]:
    """Aprende de novo a partir dos pedidos e regrava as páginas ativas."""
    target = store or BrainStore()
    minimum = load_config().profile.min_projects
    written: list[ProfileRecord] = []
    for (category, focus), hits in _grouped(target).items():
        projects = {hit.project_key for hit in hits}
        if len(projects) < minimum:
            continue
        page = f"profile/{category}/{focus}.md"
        current = target.profile_by_path(page)
        if current is not None and current.status == "tombstone":
            continue
        newest = max(hits, key=lambda hit: hit.ts)
        evidence = _evidence(hits)
        target.upsert_profile(category=category, sentence=newest.quote, page_path=page, evidence=evidence)
        saved = target.profile_by_path(page)
        if saved is None or saved.status != "active":
            continue
        _write_page(saved, evidence, target)
        written.append(saved)
    return written


def forget(rel_path: str, store: BrainStore | None = None) -> str:
    """Marca a entrada como lápide e tira a página ativa."""
    page = _page_path(rel_path)
    target = store or BrainStore()
    if not target.tombstone_profile(page):
        raise ConfigError(
            f"Não há entrada de perfil em {rel_path}. "
            "Veja as ativas com `nix brain profile list`."
        )
    _delete_page(page)
    return page


def active(store: BrainStore | None = None) -> list[ProfileRecord]:
    return (store or BrainStore()).list_profile("active")


def review(store: BrainStore | None = None) -> list[tuple[str, str, int]]:
    """Assuntos que ainda não alcançaram o mínimo de projetos."""
    target = store or BrainStore()
    minimum = load_config().profile.min_projects
    pending: list[tuple[str, str, int]] = []
    for (category, focus), hits in _grouped(target).items():
        count = len({hit.project_key for hit in hits})
        if count < minimum:
            pending.append((category, focus, count))
    return pending


def apply(store: BrainStore | None = None) -> int:
    """Regrava as páginas das entradas ativas, sem aprender de novo."""
    target = store or BrainStore()
    count = 0
    for entry in target.list_profile("active"):
        _write_page(entry, target.profile_evidence(entry.id), target)
        count += 1
    return count


def _grouped(store: BrainStore) -> dict[tuple[str, str], list[Preference]]:
    grouped: dict[tuple[str, str], list[Preference]] = {}
    names = {item.key: item.name for item in store.list_projects()}
    for project_key, project_name in names.items():
        if not resolve_project(project_key).profile_contribute:
            continue
        for session in store.sessions_for(project_key):
            for row in store.observations(session.key):
                if row.kind != "user-prompt" or not row.text:
                    continue
                for focus, quote in extract(row.text):
                    category = "tools" if focus.lower() in _TOOLS else "habits"
                    if category not in PROFILE_CATEGORIES:
                        continue
                    bucket = grouped.setdefault((category, focus.lower()), [])
                    bucket.append(
                        Preference(
                            project_key,
                            project_name or names.get(project_key, project_key),
                            quote,
                            row.ts,
                        )
                    )
    return grouped


def _evidence(hits: list[Preference]) -> list[tuple[str, str]]:
    newest: dict[str, Preference] = {}
    for hit in hits:
        current = newest.get(hit.project_key)
        if current is None or hit.ts >= current.ts:
            newest[hit.project_key] = hit
    return [(hit.project_key, hit.quote) for hit in newest.values()]


def _write_page(entry: ProfileRecord, evidence: list[tuple[str, str]], store: BrainStore) -> None:
    names = {item.key: item.name for item in store.list_projects()}
    focus = entry.page_path.rsplit("/", 1)[-1].removesuffix(".md")
    lines = [f"# {focus}", "", entry.sentence, "", "## Evidência", ""]
    if not evidence:
        lines.append("Nenhum projeto registrado.")
    for project_key, quote in evidence:
        lines.append(f"- {names.get(project_key, project_key)}: {quote}")
    lines.append("")
    body = "\n".join(lines)
    frontmatter: dict[str, object] = {
        "kind": "profile",
        "category": entry.category,
        "tags": ["perfil", entry.category],
        "title": focus,
    }
    _with_writer(entry.page_path, body, frontmatter, delete=False)


def _delete_page(page: str) -> None:
    try:
        _with_writer(page, "", None, delete=True)
    except NoteNotFoundError:
        return


def _with_writer(page: str, body: str, frontmatter: dict[str, object] | None, *, delete: bool) -> None:
    from nix.core.runtime import RuntimeHost

    config = load_config()
    if not config.brain.wiki.strip():
        raise ConfigError("O Mega Brain não tem wiki. Rode `nix brain enable --wiki NOME`.")
    host = RuntimeHost(config)
    try:
        runtime = host.resolve(config.brain.wiki)
        if delete:
            result = runtime.writer.delete_note(page, confirm=True)
        else:
            result = runtime.writer.create_note(page, body, frontmatter, overwrite=True, confirm=True)
        runtime.writeback.after_write(result)
    finally:
        host.close()


def _page_path(rel_path: str) -> str:
    cleaned = rel_path.replace("\\", "/").strip().lstrip("/")
    if not cleaned:
        raise ConfigError("Informe o caminho da entrada, por exemplo `tools/pnpm.md`.")
    if not cleaned.startswith("profile/"):
        cleaned = "profile/" + cleaned
    if not cleaned.endswith(".md"):
        cleaned += ".md"
    return cleaned
