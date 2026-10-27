"""Hooks de sessão por projeto: gerar, instalar, remover e consultar (RF-120 a RF-126).

Cada agente lê um arquivo de hook diferente, dentro do repositório. A Nix só
escreve nesses arquivos, nunca na pasta da conta (RF-122). As entradas que ela
cria são reconhecidas pelo comando `nix hook --event E --agent A`, uma marca que
não polui o esquema de nenhum agente (RF-123).

Os nomes de evento e os formatos vêm da documentação de cada agente, conferida
em outubro de 2026. O hook de `PreToolUse` fica de fora de propósito: ele roda
antes de cada ferramenta e dobraria o custo por chamada, e o resultado já chega
no `PostToolUse`.
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

from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENTS
from nix.core.sessions.store import SessionStore

_HOOK_TIMEOUT_S = 10

# `nix hook --event E --agent A` é a marca. O executável pode vir entre aspas ou depois de `& `.
_MARK = re.compile(r"(?i)\bnix(?:\.exe|\.cmd)?['\"]?\s+hook\s+--event\s+[\w-]+\s+--agent\s+[\w-]+")

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


SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        key="claude",
        label="Claude Code",
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
    ),
    AgentSpec(
        key="cursor",
        label="Cursor",
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
    ),
    AgentSpec(
        key="copilot",
        label="Copilot (VS Code e CLI)",
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
        key="devin",
        label="Devin CLI",
        rel_path=".devin/hooks.v1.json",
        layout="devin",
        events=(
            ("SessionStart", "session-start"),
            ("UserPromptSubmit", "user-prompt"),
            ("PostToolUse", "post-tool"),
            ("Stop", "stop"),
            ("PostCompaction", "compact"),
            ("SessionEnd", "session-end"),
        ),
    ),
    AgentSpec(
        key="devin-desktop",
        label="Devin Desktop",
        rel_path=".devin/hooks.json",
        layout="devin-desktop",
        events=(
            ("pre_user_prompt", "user-prompt"),
            ("post_cascade_response", "stop"),
            ("post_run_command", "post-tool"),
            ("post_write_code", "post-tool"),
            ("post_mcp_tool_use", "post-tool"),
        ),
        note=(
            "O Devin Desktop não tem evento de início nem de fim de sessão e não injeta o stdout na conversa: "
            "o handoff chega só pela ferramenta MCP `session_handoff`."
        ),
    ),
)


def spec_for(key: str) -> AgentSpec:
    for spec in SPECS:
        if spec.key == key:
            return spec
    raise ConfigError(f"Agente {key!r} desconhecido. Use um de: {', '.join(AGENTS)}.")


# -- comandos ---------------------------------------------------------------------


def _unix_command(exe: str, event: str, agent: str) -> str:
    quoted = shlex.quote(exe)
    return f"[ -x {quoted} ] && {quoted} hook --event {event} --agent {agent} || true"


def _powershell_command(exe: str, event: str, agent: str) -> str:
    safe = exe.replace("'", "''")
    return f"if (Test-Path -LiteralPath '{safe}') {{ & '{safe}' hook --event {event} --agent {agent} }}"


def _single_command(exe: str, event: str, agent: str) -> str:
    """Um só `command` para agentes sem campo por sistema. No Windows não há `[ -x ]`."""
    if sys.platform == "win32":
        return f'"{exe}" hook --event {event} --agent {agent}'
    return _unix_command(exe, event, agent)


def _entry_nested(exe: str, event: str, agent: str) -> dict[str, Any]:
    """Claude Code e Devin CLI: o comando fica dentro de uma lista `hooks`."""
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


def _entry_devin_desktop(exe: str, event: str, agent: str) -> dict[str, Any]:
    return {
        "command": _unix_command(exe, event, agent),
        "powershell": _powershell_command(exe, event, agent),
        "show_output": False,
    }


# Formato de cada entrada por `layout`: um layout novo entra aqui, sem mexer em `_entry`.
_ENTRY_BUILDERS: dict[str, Callable[[str, str, str], dict[str, Any]]] = {
    "claude": _entry_nested,
    "devin": _entry_nested,
    "cursor": _entry_cursor,
    "copilot": _entry_copilot,
    "devin-desktop": _entry_devin_desktop,
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


def _table(doc: dict[str, Any], layout: str, *, create: bool) -> dict[str, Any] | None:
    """Tabela evento → lista. No Devin CLI o arquivo inteiro é a tabela."""
    if layout == "devin":
        return doc
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
    table = _table(doc, layout, create=False)
    if table is None:
        return 0
    removed = 0
    for event in list(table):
        items = table[event]
        if not isinstance(items, list):
            continue
        kept: list[Any] = []
        for item in items:
            if layout in {"claude", "devin"} and isinstance(item, dict) and isinstance(item.get("hooks"), list):
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
    if layout != "devin" and not table:
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
    table = _table(doc, spec.layout, create=True)
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
    action: str  # criar | alterar | sem mudança
    new_text: str
    events: int


def hook_executable(command: str | None, problem: str | None) -> str:
    if not command:
        raise ConfigError(problem or "Não achei o executável da Nix. Rode `nix doctor` para ver o que falta.")
    return command.replace("\\", "/")


def plan_install(root: Path, agents: list[str], exe: str) -> list[AgentPlan]:
    plans: list[AgentPlan] = []
    for key in agents:
        spec = spec_for(key)
        path = root / spec.rel_path
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
        plans.append(AgentPlan(spec, path, existing is not None, action, text, len(spec.events)))
    return plans


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


def apply_install(plans: list[AgentPlan], root: Path, project: str, backup_dir: Path, store: SessionStore) -> list[str]:
    """Escreve os arquivos e registra o projeto para os agentes escolhidos. Devolve os backups feitos."""
    backups: list[str] = []
    for plan in plans:
        if plan.action != "sem mudança":
            if plan.exists:
                backups.append(backup_file(plan.path, root, backup_dir).as_posix())
            plan.path.parent.mkdir(parents=True, exist_ok=True)
            plan.path.write_text(plan.new_text, encoding="utf-8", newline="\n")
        store.register_project(project, plan.spec.key, plan.spec.rel_path)
    return backups


@dataclass(frozen=True)
class RemoveResult:
    spec: AgentSpec
    removed: int
    deleted_file: bool
    backup: str | None


def remove_hooks(
    root: Path, agents: list[str], project: str, backup_dir: Path, store: SessionStore
) -> list[RemoveResult]:
    """Tira só as entradas marcadas pela Nix (RF-123). O projeto deixa de aceitar eventos (RN-S1)."""
    results: list[RemoveResult] = []
    for key in agents:
        spec = spec_for(key)
        result = _remove_one(root, spec, backup_dir)
        # O registro só sai depois do arquivo: se o backup ou a escrita falharem, nada fica desalinhado.
        store.unregister_project(project, key)
        results.append(result)
    return results


def _remove_one(root: Path, spec: AgentSpec, backup_dir: Path) -> RemoveResult:
    path = root / spec.rel_path
    doc = _load(path)
    if doc is None:
        return RemoveResult(spec, 0, False, None)
    removed = strip_nix(doc, spec.layout)
    if removed == 0:
        return RemoveResult(spec, 0, False, None)
    backup = backup_file(path, root, backup_dir).as_posix()
    leftovers = {k: v for k, v in doc.items() if k not in {"version"} and v not in ({}, [])}
    if leftovers:
        path.write_text(_dump(doc), encoding="utf-8", newline="\n")
        return RemoveResult(spec, removed, False, backup)
    path.unlink()
    _prune_empty_dirs(path.parent, root)
    return RemoveResult(spec, removed, True, backup)


def _prune_empty_dirs(directory: Path, root: Path) -> None:
    """Apaga a pasta do hook (`.devin`, `.github/hooks`...) se a Nix a deixou vazia. Nunca sobe da raiz."""
    current = directory
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


@dataclass(frozen=True)
class AgentStatus:
    spec: AgentSpec
    file_exists: bool
    entries: int
    registered: bool

    @property
    def state(self) -> str:
        if self.entries and self.registered:
            return "ativo"
        if self.entries or self.registered:
            return "desalinhado"
        return "inativo"

    @property
    def hint(self) -> str:
        if self.state == "desalinhado":
            return f"Rode `nix hooks install --agent {self.spec.key}` para alinhar o arquivo e o registro."
        return ""


def status(root: Path, project: str, store: SessionStore) -> list[AgentStatus]:
    found: list[AgentStatus] = []
    for spec in SPECS:
        path = root / spec.rel_path
        try:
            doc = _load(path)
        except ConfigError:
            doc = None
        entries = count_nix(doc, spec.layout) if doc else 0
        found.append(AgentStatus(spec, path.is_file(), entries, store.has_hooks(project, spec.key)))
    return found


def unignored_files(root: Path, plans: list[AgentPlan]) -> list[str]:
    """Arquivos que levam o caminho desta máquina e ainda não estão no `.gitignore` (RF-125)."""
    out: list[str] = []
    for plan in plans:
        rel = plan.spec.rel_path
        if rel in _SELF_IGNORED:
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
    first_event = spec.events[0][1]
    entry = _entry(spec, exe, first_event)
    if "hooks" in entry:
        return str(entry["hooks"][0]["command"])
    return str(entry.get("command") or entry.get("bash") or "")
