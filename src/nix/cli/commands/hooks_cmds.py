"""nix hooks install | remove | status."""

from __future__ import annotations

from pathlib import Path

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

    print_header("hooks de sessão")
    print_plan(key, [(plan.action, plan.spec.rel_path, plan.spec.label) for plan in plans])
    if dry_run:
        for plan in plans:
            console.print()
            console.print(f"[bold]{escape(plan.spec.rel_path)}[/bold]")
            typer.echo(plan.new_text)
        print_note("Nada foi escrito (--dry-run).")
        return
    if all(plan.action == "sem mudança" for plan in plans):
        print_success("Os arquivos já estão como a Nix escreveria.")
    elif not yes and not typer.confirm("Escrever estes arquivos?", default=False):
        print_note("Nada foi escrito.")
        raise typer.Exit(code=0)

    store = SessionStore()
    backups = agent_hooks.apply_install(plans, root, key, config.safety.backup_path, store)
    print_success("[bold]Hooks ativos neste projeto.[/bold]")
    for path in backups:
        print_note(f"backup: {escape(path)}")
    for plan in plans:
        if plan.spec.note:
            print_note(f"{escape(plan.spec.label)}: {escape(plan.spec.note)}")
    _warnings(root, plans, config.sessions.enabled, bool(config.sessions.vault.strip()))
    print_note("Para orientar o agente, rode `nix skills install` neste projeto.")


def _warnings(root: Path, plans: list[agent_hooks.AgentPlan], enabled: bool, has_vault: bool) -> None:
    if not enabled:
        print_warning(
            "sessions.enabled está desligado: os hooks gravam eventos, mas as ferramentas e os comandos "
            "de sessão ficam indisponíveis. Rode `nix config set sessions.enabled true`."
        )
    if not has_vault:
        print_warning(
            "sessions.vault está vazio: as notas de sessão vão para o vault padrão, misturadas às suas. "
            "Para isolá-las, rode `nix config set sessions.vault NOME` (e `nix config set sessions.search_default "
            "incluir` se o vault for só de sessões)."
        )
    loose = agent_hooks.unignored_files(root, plans)
    if loose:
        print_warning(
            "Estes arquivos levam o caminho do binário desta máquina e não estão no .gitignore: "
            f"{', '.join(loose)}. Adicione-os ao .gitignore para não irem para o repositório."
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
        print_note("Nenhum hook da Nix está ativo neste projeto.")
        return
    config = load_config()
    for result in agent_hooks.remove_hooks(root, names, key, config.safety.backup_path, store):
        if result.removed == 0:
            print_note(f"{escape(result.spec.label)}: nada da Nix para remover em {escape(result.spec.rel_path)}.")
            continue
        end = "arquivo apagado (só havia hooks da Nix)" if result.deleted_file else "hooks do usuário preservados"
        print_success(f"{escape(result.spec.label)}: {result.removed} entradas removidas, {end}.")
        if result.backup:
            print_note(f"backup: {escape(result.backup)}")


@hooks_app.command("status", help="Mostra o que está ativo por agente")
@with_errors
def cmd_status(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    rows: list[tuple[str, str, str, str]] = []
    hints: list[str] = []
    for item in agent_hooks.status(root, key, SessionStore()):
        rows.append((item.spec.label, item.spec.rel_path, str(item.entries), item.state))
        if item.hint:
            hints.append(item.hint)
    print_header("hooks de sessão")
    print_table(f"Hooks de sessão em {key}", ("Agente", "Arquivo", "Entradas", "Estado"), rows)
    for hint in hints:
        print_warning(hint)
