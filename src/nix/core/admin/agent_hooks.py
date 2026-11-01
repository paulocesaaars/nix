"""Hooks de captura do Mega Brain: gerar, instalar, remover e consultar.

O escopo `project` usa a raiz do repositório. O escopo `global` usa a pasta
da conta. Instalar, remover e o status leem essa mesma base. O global avisa
sobre privacidade e só grava arquivo quando o caminho está confirmado; nos
demais, registra o consentimento e deixa a captura parcial. A captura continua
exigindo esse consentimento. A marca do comando é `nix brain --event E --agent A`
(ou `nix-hook brain` no binário). A marca antiga `hook` ainda é reconhecida
para ser substituída.

Os formatos de Cursor, VS Code, Claude Code e Codex vêm da documentação
conferida. O Codex grava `.codex/hooks.json` no projeto e na conta, com a
chave `hooks` e o comando aninhado. Caminhos globais também nomeados pela
documentação, relativos à pasta da conta: Cursor `.cursor/hooks.json`, Claude
`.claude/settings.json` e Codex `.codex/hooks.json`. O VS Code não tem um
arquivo único sob a home no mesmo formato: no escopo global a captura fica
parcial e nenhum JSON é inventado.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nix.core.admin.empty_dirs import prune_empty_dirs
from nix.core.brain.agents import AGENT_LABELS, AGENTS
from nix.core.brain.store import BrainStore
from nix.core.errors import ConfigError

_HOOK_TIMEOUT_S = 10

# `nix brain` no checkout e `nix-hook brain` no binário. `hook` antigo ainda é reconhecido.
_MARK = re.compile(
    r"(?i)\bnix(?:-hook)?(?:\.exe|\.cmd)?['\"]?\s+(?:hook|brain)\s+--event\s+[\w-]+\s+--agent\s+[\w-]+"
)

# O Claude Code ignora `settings.local.json` no Git sozinho. Nos demais, o arquivo leva o caminho desta máquina.
_SELF_IGNORED = {".claude/settings.local.json"}


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    rel_path: str
    layout: str
    events: tuple[tuple[str, str], ...]
    note: str = ""
    # Caminho global confirmado, relativo à pasta da conta. Vazio: não gravamos arquivo.
    global_rel: str = ""
    # Sem arquivo: o formato não foi confirmado. O consentimento ainda pode ser registrado.
    partial: bool = False


SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        key="cursor",
        label=AGENT_LABELS["cursor"],
        rel_path=".cursor/hooks.json",
        layout="cursor",
        events=(
            ("sessionStart", "session-start"),
            ("beforeSubmitPrompt", "user-prompt"),
            ("postToolUse", "post-tool"),
            ("postToolUseFailure", "post-tool"),
            ("preCompact", "compact"),
            ("stop", "stop"),
            ("sessionEnd", "session-end"),
        ),
        note="No agente na nuvem do Cursor esse hook não dispara.",
        global_rel=".cursor/hooks.json",
    ),
    AgentSpec(
        key="copilot",
        label=AGENT_LABELS["copilot"],
        rel_path=".github/hooks/nix.json",
        layout="copilot",
        events=(
            ("sessionStart", "session-start"),
            ("userPromptSubmitted", "user-prompt"),
            ("postToolUse", "post-tool"),
            ("preCompact", "compact"),
            ("agentStop", "stop"),
            ("sessionEnd", "session-end"),
        ),
        note="No Copilot na nuvem o binário da Nix não existe e o hook termina em silêncio.",
    ),
    AgentSpec(
        key="claude",
        label=AGENT_LABELS["claude"],
        rel_path=".claude/settings.local.json",
        layout="claude",
        events=(
            ("SessionStart", "session-start"),
            ("UserPromptSubmit", "user-prompt"),
            ("PostToolUse", "post-tool"),
            ("PostToolUseFailure", "post-tool"),
            ("PreCompact", "compact"),
            ("Stop", "stop"),
            ("SessionEnd", "session-end"),
        ),
        global_rel=".claude/settings.json",
    ),
    AgentSpec(
        key="codex",
        label=AGENT_LABELS["codex"],
        rel_path=".codex/hooks.json",
        layout="codex",
        events=(
            ("SessionStart", "session-start"),
            ("UserPromptSubmit", "user-prompt"),
            ("PostToolUse", "post-tool"),
            ("PreCompact", "compact"),
            ("Stop", "stop"),
            ("SessionEnd", "session-end"),
        ),
        global_rel=".codex/hooks.json",
        note="O Codex só executa o hook depois de confiar em /hooks.",
    ),
)


# `nix brain hooks install --all` usa esta ordem, a mesma de `AGENTS`.
CONFIRMED_CLIENTS: tuple[str, ...] = AGENTS


def spec_for(key: str) -> AgentSpec:
    for spec in SPECS:
        if spec.key == key:
            return spec
    raise ConfigError(f"Agente {key!r} desconhecido. Use um de: {', '.join(AGENTS)}.")


# -- comandos ---------------------------------------------------------------------


def _unix_command(exe: str, event: str, agent: str) -> str:
    quoted = shlex.quote(exe)
    return f"[ -x {quoted} ] && {quoted} brain --event {event} --agent {agent} || true"


def _powershell_command(exe: str, event: str, agent: str) -> str:
    safe = exe.replace("'", "''")
    return f"if (Test-Path -LiteralPath '{safe}') {{ & '{safe}' brain --event {event} --agent {agent} }}"


def _single_command(exe: str, event: str, agent: str) -> str:
    """Um só `command` para agentes sem campo por sistema. No Windows não há `[ -x ]`."""
    if sys.platform == "win32":
        return f'"{exe}" brain --event {event} --agent {agent}'
    return _unix_command(exe, event, agent)


def _entry_nested(exe: str, event: str, agent: str) -> dict[str, Any]:
    """Claude Code e Codex: o comando fica dentro de uma lista `hooks`."""
    handler = {"type": "command", "command": _single_command(exe, event, agent), "timeout": _HOOK_TIMEOUT_S}
    return {"hooks": [handler]}


def _entry_cursor(exe: str, event: str, agent: str) -> dict[str, Any]:
    return {"command": _single_command(exe, event, agent), "timeout": _HOOK_TIMEOUT_S}


def _entry_copilot(exe: str, event: str, agent: str) -> dict[str, Any]:
    return {
        "type": "command",
        "bash": _unix_command(exe, event, agent),
        "powershell": _powershell_command(exe, event, agent),
        "timeoutSec": _HOOK_TIMEOUT_S,
    }


# Formato de cada entrada por `layout`: um layout novo entra aqui, sem mexer em `_entry`.
_ENTRY_BUILDERS: dict[str, Callable[[str, str, str], dict[str, Any]]] = {
    "claude": _entry_nested,
    "codex": _entry_nested,
    "cursor": _entry_cursor,
    "copilot": _entry_copilot,
}


def _entry(spec: AgentSpec, exe: str, nix_event: str) -> dict[str, Any]:
    return _ENTRY_BUILDERS[spec.layout](exe, nix_event, spec.key)


# -- documento -----------------------------------------------------------------------


def _is_nix(value: Any) -> bool:
    return isinstance(value, str) and _MARK.search(value) is not None


def _entry_is_nix(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    return any(_is_nix(entry.get(key)) for key in ("command", "bash", "powershell"))


def _table(doc: dict[str, Any], *, create: bool) -> dict[str, Any] | None:
    """Tabela evento → lista, na chave `hooks`."""
    table = doc.get("hooks")
    if isinstance(table, dict):
        return table
    if create:
        doc["hooks"] = {}
        table = doc["hooks"]
        return table  # type: ignore[no-any-return]
    return None


def strip_nix(doc: dict[str, Any], layout: str) -> int:
    """Tira as entradas da Nix e devolve quantas saíram. Entradas do usuário ficam."""
    table = _table(doc, create=False)
    if table is None:
        return 0
    removed = 0
    for event in list(table):
        items = table[event]
        if not isinstance(items, list):
            continue
        kept: list[Any] = []
        for item in items:
            nested = layout in {"claude", "codex"}
            if nested and isinstance(item, dict) and isinstance(item.get("hooks"), list):
                inner = [h for h in item["hooks"] if not _entry_is_nix(h)]
                removed += len(item["hooks"]) - len(inner)
                if inner:
                    kept.append({**item, "hooks": inner})
            elif _entry_is_nix(item):
                removed += 1
            else:
                kept.append(item)
        if kept:
            table[event] = kept
        else:
            del table[event]
    if not table:
        doc.pop("hooks", None)
    return removed


def count_nix(doc: dict[str, Any], layout: str) -> int:
    copy = json.loads(json.dumps(doc))
    return strip_nix(copy, layout)


def build_document(existing: dict[str, Any] | None, spec: AgentSpec, exe: str) -> dict[str, Any]:
    """O arquivo com as entradas da Nix no lugar. Rodar de novo troca as dela, sem duplicar (RF-124)."""
    doc: dict[str, Any] = json.loads(json.dumps(existing)) if existing else {}
    strip_nix(doc, spec.layout)
    if spec.layout in {"cursor", "copilot"}:
        doc.setdefault("version", 1)
    table = _table(doc, create=True)
    if table is None:
        raise ConfigError(f"Não foi possível montar a tabela de hooks de {spec.label}. Reporte este erro.")
    for agent_event, nix_event in spec.events:
        table.setdefault(agent_event, []).append(_entry(spec, exe, nix_event))
    return doc


def _dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{path.as_posix()} não é um JSON válido ({exc}). Corrija ou mova o arquivo e rode de novo; "
            "a Nix não sobrescreve um arquivo que ela não consegue ler."
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path.as_posix()} não tem um objeto JSON na raiz. Corrija ou mova o arquivo e rode de novo."
        )
    return data


# -- plano, instalação, remoção e estado ------------------------------------------------


@dataclass(frozen=True)
class AgentPlan:
    spec: AgentSpec
    path: Path
    exists: bool
    action: str  # criar | alterar | sem mudança | parcial
    new_text: str
    events: int
    scope: str = "project"


def hook_executable(command: str | None, problem: str | None) -> str:
    if not command:
        raise ConfigError(problem or "Não achei o executável da Nix. Rode `nix doctor` para ver o que falta.")
    return command.replace("\\", "/")


def _scope_base(root: Path, scope: str) -> Path:
    """Pasta da conta no global; raiz do repositório no project."""
    return Path.home() if scope == "global" else root


def _scope_relative(spec: AgentSpec, scope: str) -> str:
    return spec.global_rel if scope == "global" else spec.rel_path


def plan_install(root: Path, agents: list[str], exe: str, *, scope: str = "project") -> list[AgentPlan]:
    if scope not in {"project", "global"}:
        raise ConfigError("Escopo inválido. Use global ou project.")
    plans: list[AgentPlan] = []
    for key in agents:
        spec = spec_for(key)
        if _fileless(spec, scope):
            plans.append(AgentPlan(spec, root, False, "parcial", "", 0, scope))
            continue
        rel = _scope_relative(spec, scope)
        base = _scope_base(root, scope)
        path = base / rel
        existing = _load(path)
        doc = build_document(existing, spec, exe)
        text = _dump(doc)
        current = path.read_text(encoding="utf-8") if existing is not None else None
        if current is None:
            action = "criar"
        elif current == text:
            action = "sem mudança"
        else:
            action = "alterar"
        plans.append(AgentPlan(spec, path, existing is not None, action, text, len(spec.events), scope))
    return plans


def _fileless(spec: AgentSpec, scope: str) -> bool:
    """Sem arquivo confirmado: agente parcial, ou global sem caminho conhecido."""
    if spec.partial or not spec.layout:
        return True
    if scope == "global" and not spec.global_rel:
        return True
    return not spec.rel_path


def backup_file(path: Path, root: Path, backup_dir: Path) -> Path:
    """Cópia antes de alterar um arquivo existente (RF-124)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dest = backup_dir / "hooks" / stamp / root.name / path.relative_to(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(path, dest)
    except OSError as exc:
        raise ConfigError(
            f"Não foi possível salvar o backup de {path.as_posix()} em {dest.as_posix()}: {exc}. "
            "Verifique safety.backup_dir e o espaço em disco."
        ) from exc
    return dest


def _write_utf8(path: Path, text: str) -> None:
    """Grava UTF-8 com quebra LF.

    `open()` no lugar de `Path.write_text(newline=)`: esse argumento só existe no
    Python 3.13, e o binário publicado é compilado com 3.12.
    """
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def apply_install(plans: list[AgentPlan], root: Path, project: str, backup_dir: Path, store: BrainStore) -> list[str]:
    """Escreve os arquivos confirmados e registra o consentimento. Devolve os backups feitos."""
    backups: list[str] = []
    for plan in plans:
        if plan.action not in {"sem mudança", "parcial"}:
            anchor = _scope_base(root, plan.scope)
            if plan.exists:
                backups.append(backup_file(plan.path, anchor, backup_dir).as_posix())
            plan.path.parent.mkdir(parents=True, exist_ok=True)
            _write_utf8(plan.path, plan.new_text)
        hook_file = "" if plan.action == "parcial" else plan.spec.rel_path
        store.register_hook(
            scope=plan.scope,
            agent=plan.spec.key,
            project_key="" if plan.scope == "global" else project,
            hook_file=hook_file,
        )
    return backups


@dataclass(frozen=True)
class RemoveResult:
    spec: AgentSpec
    removed: int
    deleted_file: bool
    backup: str | None


def remove_hooks(
    root: Path,
    agents: list[str],
    project: str,
    backup_dir: Path,
    store: BrainStore,
    *,
    scope: str = "project",
) -> list[RemoveResult]:
    """Tira só as entradas marcadas pela Nix e o consentimento daquele escopo."""
    if scope not in {"project", "global"}:
        raise ConfigError("Escopo inválido. Use global ou project.")
    results: list[RemoveResult] = []
    for key in agents:
        spec = spec_for(key)
        if _fileless(spec, scope):
            result = RemoveResult(spec, 0, False, None)
        else:
            result = _remove_one(root, spec, backup_dir, scope)
        store.unregister_hook(scope=scope, agent=key, project_key="" if scope == "global" else project)
        results.append(result)
    return results


def _remove_one(root: Path, spec: AgentSpec, backup_dir: Path, scope: str) -> RemoveResult:
    base = _scope_base(root, scope)
    path = base / _scope_relative(spec, scope)
    doc = _load(path)
    if doc is None:
        return RemoveResult(spec, 0, False, None)
    removed = strip_nix(doc, spec.layout)
    if removed == 0:
        return RemoveResult(spec, 0, False, None)
    backup = backup_file(path, base, backup_dir).as_posix()
    leftovers = {k: v for k, v in doc.items() if k not in {"version"} and v not in ({}, [])}
    if leftovers:
        _write_utf8(path, _dump(doc))
        return RemoveResult(spec, removed, False, backup)
    path.unlink()
    prune_empty_dirs(path.parent, base)
    return RemoveResult(spec, removed, True, backup)


@dataclass(frozen=True)
class AgentStatus:
    spec: AgentSpec
    file_exists: bool
    entries: int
    registered: bool
    mismatched_scopes: tuple[str, ...] = ()
    fileless_consent: bool = False

    @property
    def state(self) -> str:
        if self.mismatched_scopes:
            return "desalinhado"
        if self.entries and self.registered:
            return "ativo"
        if self.fileless_consent or (self.spec.partial and self.registered):
            return "parcial"
        return "inativo"

    @property
    def hint(self) -> str:
        if not self.mismatched_scopes:
            return ""
        names = " e ".join(self.mismatched_scopes)
        steps = " ".join(
            (
                f"Rode `nix brain hooks install --scope {scope} --agent {self.spec.key}` "
                f"para alinhar o escopo {scope}."
            )
            for scope in self.mismatched_scopes
        )
        return f"O arquivo e o consentimento divergem no escopo {names}. {steps}"


def _nix_entries(path: Path, layout: str) -> int:
    """Entradas da Nix no arquivo. JSON ilegível conta como zero, para o status não abortar."""
    if not path.is_file():
        return 0
    try:
        doc = _load(path)
    except ConfigError:
        return 0
    if not doc:
        return 0
    return count_nix(doc, layout)


def status(root: Path, project: str, store: BrainStore) -> list[AgentStatus]:
    """Confronta, em cada escopo, o arquivo daquela base com o consentimento daquele escopo."""
    consents = {(agent, item_scope) for agent, item_scope in store.installed_agents(project)}
    found: list[AgentStatus] = []
    for spec in SPECS:
        mismatched: list[str] = []
        entries = 0
        file_exists = False
        registered = False
        fileless_consent = False
        for item_scope in ("project", "global"):
            has_consent = (spec.key, item_scope) in consents
            registered = registered or has_consent
            if _fileless(spec, item_scope):
                if has_consent:
                    fileless_consent = True
                continue
            path = _scope_base(root, item_scope) / _scope_relative(spec, item_scope)
            file_exists = file_exists or path.is_file()
            count = _nix_entries(path, spec.layout)
            entries += count
            if count and has_consent:
                continue
            if count or has_consent:
                mismatched.append(item_scope)
        found.append(
            AgentStatus(spec, file_exists, entries, registered, tuple(mismatched), fileless_consent)
        )
    return found


def unignored_files(root: Path, plans: list[AgentPlan]) -> list[str]:
    """Arquivos que levam o caminho desta máquina e ainda não estão no `.gitignore` (RF-125)."""
    out: list[str] = []
    for plan in plans:
        rel = plan.spec.rel_path
        if not rel or plan.scope != "project" or plan.action == "parcial" or rel in _SELF_IGNORED:
            continue
        try:
            done = subprocess.run(
                ["git", "check-ignore", "-q", "--", rel],  # noqa: S607
                cwd=root,
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if done.returncode == 1:
            out.append(rel)
        elif done.returncode not in {0, 1}:
            return []
    return out


def command_preview(spec: AgentSpec, exe: str) -> str:
    """Uma linha de comando de exemplo, para a tela Conectar clientes."""
    if spec.partial or not spec.events or not spec.layout:
        return ""
    first_event = spec.events[0][1]
    entry = _entry(spec, exe, first_event)
    if "hooks" in entry:
        return str(entry["hooks"][0]["command"])
    return str(entry.get("command") or entry.get("bash") or "")
