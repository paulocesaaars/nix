"""`nix run`: liga o hook e o MCP se faltarem e entrega o histórico anterior."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from nix.config.executables import packaged_hook_executable
from nix.config.loader import load_config
from nix.core.admin import agent_hooks
from nix.core.admin.doctor import nix_command
from nix.core.brain.agents import AGENTS
from nix.core.brain.events import find_project
from nix.core.brain.history import find_previous_history
from nix.core.brain.history.stage import discard, stage_readonly
from nix.core.brain.store import BrainStore
from nix.core.errors import ConfigError

# Arquivos MCP já descritos em `client_config`. Os outros agentes não têm formato confirmado.
_MCP_PROJECT: dict[str, tuple[str, str]] = {
    "claude": (".mcp.json", "mcpServers"),
    "cursor": (".cursor/mcp.json", "mcpServers"),
    "copilot": (".vscode/mcp.json", "servers"),
}


def launch(agent: str, extra: list[str], *, project: str | None = None, autowire: bool = True) -> int:
    """Sobe o agente. Apaga a cópia do histórico quando ele termina."""
    key = agent.strip().lower()
    if key not in AGENTS:
        raise ConfigError(f"Agente {agent!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    project_key, _name = find_project(project or "")
    folder = Path(project_key)
    notes: list[str] = []
    if autowire:
        notes.extend(_ensure_hook(folder, project_key, key))
        notes.extend(_ensure_mcp(folder, key))
    else:
        notes.append("Autowire desligado: hook e MCP não foram alterados.")
    source = find_previous_history(key, folder)
    staged: Path | None = None
    env = os.environ.copy()
    if source is None:
        notes.append(
            f"Sem histórico nativo confirmado para {key} neste projeto. "
            "O agente segue sem NIX_PREVIOUS_SESSION_HISTORY."
        )
    else:
        staged = stage_readonly(source)
        env["NIX_PREVIOUS_SESSION_HISTORY"] = str(staged)
    _emit(notes)
    command = [key, *extra]
    if shutil.which(key) is None:
        discard(staged)
        raise ConfigError(
            f"Não achei o executável {key!r} no PATH. Instale o agente ou informe o comando certo."
        )
    try:
        completed = subprocess.run(command, env=env, check=False)
        return int(completed.returncode)
    finally:
        discard(staged)


def _ensure_hook(root: Path, project_key: str, agent: str) -> list[str]:
    exe = _hook_exe()
    plans = agent_hooks.plan_install(root, [agent], exe, scope="project")
    pending = [plan for plan in plans if plan.action != "sem mudança"]
    if not pending:
        return []
    agent_hooks.apply_install(plans, root, project_key, load_config().safety.backup_path, BrainStore())
    if plans[0].action == "parcial":
        return [f"{plans[0].spec.label}: captura parcial. Nenhum arquivo de hook foi gravado."]
    return [f"Hook de {plans[0].spec.label} instalado em {plans[0].path.as_posix()}."]


def _ensure_mcp(root: Path, agent: str) -> list[str]:
    spec = _MCP_PROJECT.get(agent)
    if spec is None:
        return [f"O arquivo MCP de {agent} não está confirmado. O servidor nix não foi gravado."]
    rel, table = spec
    path = root / rel
    command = _nix_command()
    entry = {"command": command} if table == "mcpServers" else {"type": "stdio", "command": command}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [f"{rel} não é um JSON válido. Não alterei o MCP. Corrija o arquivo e rode de novo."]
        if not isinstance(data, dict):
            return [f"{rel} não tem um objeto na raiz. Não alterei o MCP."]
        servers = data.get(table)
        if isinstance(servers, dict) and "nix" in servers:
            return []
        if not isinstance(servers, dict):
            servers = {}
        servers["nix"] = entry
        data[table] = servers
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        agent_hooks.backup_file(path, root, load_config().safety.backup_path)
        _write(path, text)
        return [f"Servidor nix acrescentado em {rel}."]
    text = json.dumps({table: {"nix": entry}}, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, text)
    return [f"Servidor nix gravado em {rel}."]


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _hook_exe() -> str:
    sibling = packaged_hook_executable()
    if sibling is not None:
        return agent_hooks.hook_executable(str(sibling), None)
    return agent_hooks.hook_executable(*nix_command())


def _nix_command() -> str:
    command, problem = nix_command()
    if not command:
        raise ConfigError(problem or "Não achei o executável da Nix. Rode `nix doctor`.")
    return command.replace("\\", "/")


def _emit(notes: list[str]) -> None:
    for note in notes:
        sys.stderr.write(note + "\n")
