"""Skills de produto por projeto: instalar, remover e consultar.

A Nix copia só as skills que vêm no pacote, para a pasta que cada agente lê.
A marca é o arquivo `.nix-skill` com o nome da skill. `remove` apaga só as
pastas com essa marca e não mexe nas skills de desenvolvimento.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from nix.core.admin.empty_dirs import prune_empty_dirs
from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENT_LABELS, AGENTS

# Nova skill entra aqui e em src/nix/skills/<nome>/SKILL.md.
SKILLS: tuple[str, ...] = ("sessoes-nix",)
MARKER = ".nix-skill"


@dataclass(frozen=True)
class SkillDestination:
    rel_dir: str
    agents: tuple[str, ...]


# Cursor, Copilot e Devin leem a mesma pasta. O Devin também encontra
# `.claude/skills`; a pasta recomendada na documentação dele é `.agents/skills`.
DESTINATIONS: tuple[SkillDestination, ...] = (
    SkillDestination(".claude/skills", ("claude",)),
    SkillDestination(".agents/skills", ("cursor", "copilot", "devin", "devin-desktop")),
)


def reader_label(destination: SkillDestination) -> str:
    return ", ".join(AGENT_LABELS[key] for key in destination.agents)


def _unix_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def skill_markdown(name: str) -> str:
    """Texto da skill como vem no pacote."""
    resource = files("nix.skills").joinpath(name, "SKILL.md")
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(f"A skill {name} não está neste executável. Reinstale a Nix.") from exc
    text = _unix_text(text)
    if not text.startswith("---\n"):
        raise ConfigError(f"A skill {name} veio sem o bloco de descrição. Reinstale a Nix.")
    return text


def marker_text(name: str) -> str:
    return f"{name}\n"


def selected_destinations(agents: list[str]) -> list[SkillDestination]:
    """Pastas dos agentes pedidos, sem repetir a que dois agentes compartilham.

    Recusa agente que não está em `DESTINATIONS`: sem pasta, o install não
    pode responder que já está tudo certo.
    """
    chosen = _known_agents(agents)
    found: list[SkillDestination] = []
    missing: list[str] = []
    for key in chosen:
        matches = [item for item in DESTINATIONS if key in item.agents]
        if not matches:
            missing.append(key)
            continue
        if matches[0] not in found:
            found.append(matches[0])
    if missing:
        known = ", ".join(f"{item.rel_dir} ({reader_label(item)})" for item in DESTINATIONS)
        raise ConfigError(
            f"Não há pasta de skill para: {', '.join(missing)}. Pastas conhecidas: {known}. "
            "Acrescente o agente em nix.core.admin.agent_skills.DESTINATIONS e rode de novo."
        )
    return found


def _known_agents(agents: list[str]) -> list[str]:
    names = list(dict.fromkeys(agents))
    unknown = [name for name in names if name not in AGENTS]
    if unknown:
        raise ConfigError(f"Agente {unknown[0]!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    if not names:
        raise ConfigError("Nenhum agente foi escolhido. Rode de novo e informe `--agent`.")
    return names


def skill_rel(destination: SkillDestination, name: str) -> str:
    return f"{destination.rel_dir}/{name}"


@dataclass(frozen=True)
class SkillPlan:
    name: str
    destination: SkillDestination
    path: Path
    action: str  # criar | alterar | sem mudança

    @property
    def rel(self) -> str:
        return skill_rel(self.destination, self.name)


def plan_install(root: Path, agents: list[str]) -> list[SkillPlan]:
    """O que seria escrito. Recusa pasta que já existe sem a marca da Nix."""
    plans: list[SkillPlan] = []
    occupied: list[str] = []
    for destination in selected_destinations(agents):
        for name in SKILLS:
            path = root / destination.rel_dir / name
            owned = _ownership(path, name)
            rel = skill_rel(destination, name)
            if owned is False:
                occupied.append(rel)
                continue
            action = "criar" if owned is None else ("sem mudança" if _same(path, name) else "alterar")
            plans.append(SkillPlan(name, destination, path, action))
    if occupied:
        joined = ", ".join(occupied)
        raise ConfigError(
            f"Estes caminhos já existem e não foram criados pela Nix: {joined}. "
            "Renomeie ou apague cada um e rode `nix skills install` de novo."
        )
    return plans


def _ownership(path: Path, name: str) -> bool | None:
    """True se a marca é desta skill, False se o caminho está ocupado, None se não existe."""
    if not path.exists():
        return None
    marker = path / MARKER
    if not path.is_dir() or not marker.is_file():
        return False
    try:
        content = marker.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Não consegui ler {marker.as_posix()}. Verifique a permissão da pasta e rode de novo."
        ) from exc
    return _unix_text(content) == marker_text(name)


def _same(path: Path, name: str) -> bool:
    skill = path / "SKILL.md"
    if not skill.is_file():
        return False
    try:
        current = skill.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Não consegui ler {skill.as_posix()}. Verifique a permissão da pasta e rode de novo."
        ) from exc
    return _unix_text(current) == skill_markdown(name)


def backup_tree(path: Path, root: Path, backup_dir: Path) -> Path:
    """Cópia da pasta da skill antes de alterar ou apagar."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise ConfigError(f"A skill {path.as_posix()} está fora do projeto {root.as_posix()}.") from exc
    dest = backup_dir / "skills" / stamp / root.name / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(path, dest)
    except OSError as exc:
        raise ConfigError(
            f"Não foi possível salvar o backup de {path.as_posix()} em {dest.as_posix()}: {exc}. "
            "Verifique safety.backup_dir e o espaço em disco."
        ) from exc
    return dest


def apply_install(plans: list[SkillPlan], root: Path, backup_dir: Path) -> list[str]:
    """Escreve as pastas. Devolve os backups feitos."""
    backups: list[str] = []
    for plan in plans:
        if plan.action == "sem mudança":
            continue
        if plan.action == "alterar":
            backups.append(backup_tree(plan.path, root, backup_dir).as_posix())
        _write(plan.path, plan.name)
    return backups


def _write(path: Path, name: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        # A marca vem primeiro: se o SKILL.md não chegar a ser gravado, a pasta
        # fica desatualizada e o próximo install repara, em vez de recusar.
        (path / MARKER).write_text(marker_text(name), encoding="utf-8", newline="\n")
        (path / "SKILL.md").write_text(skill_markdown(name), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ConfigError(
            f"Não foi possível escrever {path.as_posix()}: {exc}. Verifique a permissão da pasta do projeto."
        ) from exc


@dataclass(frozen=True)
class RemoveResult:
    destination: SkillDestination
    name: str
    removed: bool
    backup: str | None

    @property
    def rel(self) -> str:
        return skill_rel(self.destination, self.name)


def remove_skills(root: Path, agents: list[str], backup_dir: Path) -> list[RemoveResult]:
    """Apaga só as pastas marcadas pela Nix."""
    results: list[RemoveResult] = []
    for destination in selected_destinations(agents):
        for name in SKILLS:
            path = root / destination.rel_dir / name
            if _ownership(path, name) is not True:
                results.append(RemoveResult(destination, name, False, None))
                continue
            backup = backup_tree(path, root, backup_dir).as_posix()
            try:
                shutil.rmtree(path)
            except OSError as exc:
                raise ConfigError(
                    f"Não foi possível apagar {path.as_posix()}: {exc}. "
                    "Feche o que estiver usando a pasta e rode `nix skills remove` de novo."
                ) from exc
            prune_empty_dirs(path.parent, root)
            results.append(RemoveResult(destination, name, True, backup))
    return results


@dataclass(frozen=True)
class SkillStatus:
    destination: SkillDestination
    name: str
    state: str

    @property
    def rel(self) -> str:
        return skill_rel(self.destination, self.name)

    @property
    def hint(self) -> str:
        if self.state == "desatualizada":
            return f"Rode `nix skills install` para atualizar {self.rel}."
        if self.state == "ocupada":
            return (
                f"O caminho {self.rel} já existe e não foi criado pela Nix. "
                "Renomeie ou apague e rode `nix skills install`."
            )
        return ""


def status(root: Path) -> list[SkillStatus]:
    found: list[SkillStatus] = []
    for destination in DESTINATIONS:
        for name in SKILLS:
            path = root / destination.rel_dir / name
            found.append(SkillStatus(destination, name, _state(path, name)))
    return found


def _state(path: Path, name: str) -> str:
    owned = _ownership(path, name)
    if owned is None:
        return "inativa"
    if not owned:
        return "ocupada"
    if _same(path, name):
        return "ativa"
    return "desatualizada"
