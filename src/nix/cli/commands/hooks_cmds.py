"""nix hooks install | remove | status."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape

from nix.cli.agents import choose_agents, project_root
from nix.cli.deps import with_errors
from nix.cli.render import console
from nix.config.executables import packaged_hook_executable
from nix.config.loader import load_config
from nix.core.admin import agent_hooks
from nix.core.admin.doctor import nix_command
from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENTS
from nix.core.sessions.store import SessionStore

hooks_app = typer.Typer(
    help="Ativa, remove e mostra os hooks de sessão no repositório atual.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _agents(requested: list[str] | None) -> list[str]:
    """Agentes pedidos ou escolhidos na hora. Nenhum vem marcado (RF-121)."""
    return choose_agents(
        requested,
        command="nix hooks install",
        question=lambda key: f"Ativar {agent_hooks.spec_for(key).label}?",
    )


def _hook_exe() -> str:
    """No binário publicado o agente chama o `nix-hook`, que cabe nos 300 ms."""
    sibling = packaged_hook_executable()
    if sibling is not None:
        return agent_hooks.hook_executable(str(sibling), None)
    return agent_hooks.hook_executable(*nix_command())


@hooks_app.command("install", help="Ativa os hooks de sessão neste repositório")
@with_errors
def cmd_install(
    agent: list[str] | None = typer.Option(None, "--agent", help=f"Agente ({', '.join(AGENTS)}). Repita para vários."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que seria escrito"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação"),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    agents = _agents(agent)
    exe = _hook_exe()
    plans = agent_hooks.plan_install(root, agents, exe)
    config = load_config()

    console.print(f"Projeto: {escape(key)}")
    for plan in plans:
        console.print(f"  {plan.action:<12} {escape(plan.spec.rel_path)}  [dim]{escape(plan.spec.label)}[/dim]")
    if dry_run:
        for plan in plans:
            console.print(f"\n[bold]{escape(plan.spec.rel_path)}[/bold]")
            typer.echo(plan.new_text)
        console.print("[dim]Nada foi escrito (--dry-run).[/dim]")
        return
    if all(plan.action == "sem mudança" for plan in plans):
        console.print("Os arquivos já estão como a Nix escreveria.")
    elif not yes and not typer.confirm("Escrever estes arquivos?", default=False):
        console.print("Nada foi escrito.")
        raise typer.Exit(code=0)

    store = SessionStore()
    backups = agent_hooks.apply_install(plans, root, key, config.safety.backup_path, store)
    console.print("[green]Hooks ativos neste projeto.[/green]")
    for path in backups:
        console.print(f"  backup: {escape(path)}")
    for plan in plans:
        if plan.spec.note:
            console.print(f"[dim]{escape(plan.spec.label)}: {escape(plan.spec.note)}[/dim]")
    _warnings(root, plans, config.sessions.enabled, bool(config.sessions.vault.strip()))
    console.print("[dim]Para orientar o agente, rode `nix skills install` neste projeto.[/dim]")


def _warnings(root: Path, plans: list[agent_hooks.AgentPlan], enabled: bool, has_vault: bool) -> None:
    if not enabled:
        console.print(
            "[yellow]sessions.enabled está desligado: os hooks gravam eventos, mas as ferramentas e os comandos "
            "de sessão ficam indisponíveis. Rode `nix config set sessions.enabled true`.[/yellow]"
        )
    if not has_vault:
        console.print(
            "[yellow]sessions.vault está vazio: as notas de sessão vão para o vault padrão, misturadas às suas. "
            "Para isolá-las, rode `nix config set sessions.vault NOME` (e `nix config set sessions.search_default "
            "incluir` se o vault for só de sessões).[/yellow]"
        )
    loose = agent_hooks.unignored_files(root, plans)
    if loose:
        console.print(
            "[yellow]Estes arquivos levam o caminho do binário desta máquina e não estão no .gitignore: "
            f"{escape(', '.join(loose))}. Adicione-os ao .gitignore para não irem para o repositório.[/yellow]"
        )


@hooks_app.command("remove", help="Remove só os hooks que a Nix colocou")
@with_errors
def cmd_remove(
    agent: list[str] | None = typer.Option(None, "--agent", help="Agente. Sem opção, todos os que a Nix ativou."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    store = SessionStore()
    names = [item.strip().lower() for item in (agent or []) if item.strip()]
    for name in names:
        if name not in AGENTS:
            raise ConfigError(f"Agente {name!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
    if not names:
        names = [item.spec.key for item in agent_hooks.status(root, key, store) if item.entries or item.registered]
    if not names:
        console.print("Nenhum hook da Nix está ativo neste projeto.")
        return
    config = load_config()
    for result in agent_hooks.remove_hooks(root, names, key, config.safety.backup_path, store):
        if result.removed == 0:
            console.print(f"{escape(result.spec.label)}: nada da Nix para remover em {escape(result.spec.rel_path)}.")
            continue
        end = "arquivo apagado (só havia hooks da Nix)" if result.deleted_file else "hooks do usuário preservados"
        console.print(f"{escape(result.spec.label)}: {result.removed} entradas removidas, {end}.")
        if result.backup:
            console.print(f"  backup: {escape(result.backup)}")


@hooks_app.command("status", help="Mostra o que está ativo por agente")
@with_errors
def cmd_status(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    from rich.table import Table

    table = Table(title=f"Hooks de sessão em {key}")
    for column in ("Agente", "Arquivo", "Entradas", "Estado"):
        table.add_column(column)
    hints: list[str] = []
    for item in agent_hooks.status(root, key, SessionStore()):
        table.add_row(item.spec.label, item.spec.rel_path, str(item.entries), item.state)
        if item.hint:
            hints.append(item.hint)
    console.print(table)
    for hint in hints:
        console.print(f"[yellow]{escape(hint)}[/yellow]")
