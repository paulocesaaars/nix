"""nix skills install | remove | status."""

from __future__ import annotations

import typer
from rich.markup import escape

from nix.cli.agents import choose_agents, project_root
from nix.cli.deps import with_errors
from nix.cli.render import (
    console,
    print_header,
    print_note,
    print_plan,
    print_success,
    print_table,
    print_warning,
)
from nix.config.loader import load_config
from nix.core.admin import agent_skills
from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENT_LABELS, AGENTS

skills_app = typer.Typer(
    help="Instala, remove e mostra as skills da Nix no repositório atual.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _agents(requested: list[str] | None) -> list[str]:
    """Agentes pedidos ou escolhidos na hora. Nenhum vem marcado."""
    return choose_agents(
        requested,
        command="nix skills install",
        question=lambda key: f"Instalar para {AGENT_LABELS[key]}?",
    )


@skills_app.command("install", help="Copia as skills da Nix para os agentes deste repositório")
@with_errors
def cmd_install(
    agent: list[str] | None = typer.Option(None, "--agent", help=f"Agente ({', '.join(AGENTS)}). Repita para vários."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que seria escrito"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação"),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    plans = agent_skills.plan_install(root, _agents(agent))
    if not plans:
        raise ConfigError(
            "Nenhuma pasta de skill corresponde aos agentes escolhidos. "
            "Rode `nix skills status` para ver as pastas e tente de novo."
        )

    print_header("skills da Nix")
    print_plan(key, [(plan.action, plan.rel, agent_skills.reader_label(plan.destination)) for plan in plans])
    if dry_run:
        shown: set[str] = set()
        for plan in plans:
            if plan.name in shown:
                continue
            shown.add(plan.name)
            console.print()
            console.print(f"[bold]{escape(plan.name)}/SKILL.md[/bold]")
            typer.echo(agent_skills.skill_markdown(plan.name))
        print_note("Nada foi escrito (--dry-run).")
        return
    if all(plan.action == "sem mudança" for plan in plans):
        print_success("As skills já estão como a Nix escreveria.")
        return
    if not yes and not typer.confirm("Escrever estas skills?", default=False):
        print_note("Nada foi escrito.")
        raise typer.Exit(code=0)

    backups = agent_skills.apply_install(plans, root, load_config().safety.backup_path)
    print_success("[bold]Skills da Nix ativas neste projeto.[/bold]")
    for path in backups:
        print_note(f"backup: {escape(path)}")


@skills_app.command("remove", help="Remove só as skills que a Nix colocou")
@with_errors
def cmd_remove(
    agent: list[str] | None = typer.Option(None, "--agent", help="Agente. Sem opção, todas as skills da Nix."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    names = [item.strip().lower() for item in (agent or []) if item.strip()]
    for name in names:
        if name not in AGENTS:
            raise ConfigError(f"Agente {name!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    explicit = bool(names)
    if not names:
        names = list(AGENTS)
    print_header("skills da Nix")
    results = agent_skills.remove_skills(root, names, load_config().safety.backup_path)
    printed = False
    for result in results:
        if not result.removed and not explicit:
            continue
        printed = True
        readers = agent_skills.reader_label(result.destination)
        if not result.removed:
            print_note(f"{escape(readers)}: nada da Nix para remover em {escape(result.rel)}.")
            continue
        print_success(f"{escape(readers)}: skill {escape(result.name)} removida de {escape(result.rel)}.")
        if result.backup:
            print_note(f"backup: {escape(result.backup)}")
    if not printed:
        print_note(f"Nenhuma skill da Nix está em {escape(key)}.")


@skills_app.command("status", help="Mostra as skills da Nix por pasta de agente")
@with_errors
def cmd_status(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    rows: list[tuple[str, str, str, str]] = []
    hints: list[str] = []
    for item in agent_skills.status(root):
        rows.append((item.name, item.rel, agent_skills.reader_label(item.destination), item.state))
        if item.hint:
            hints.append(item.hint)
    print_header("skills da Nix")
    print_table(f"Skills da Nix em {key}", ("Skill", "Pasta", "Quem lê", "Estado"), rows)
    for hint in hints:
        print_warning(hint)
