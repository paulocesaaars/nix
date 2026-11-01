"""nix brain enable | status | hooks | work."""

from __future__ import annotations

import sys

import typer

from nix.cli.agents import choose_agents, project_root
from nix.cli.deps import with_errors
from nix.cli.render import print_header, print_note, print_plan, print_success, print_table, print_warning
from nix.config.editor import set_value
from nix.config.executables import packaged_hook_executable
from nix.config.loader import load_config
from nix.core.admin import agent_hooks
from nix.core.admin.doctor import nix_command
from nix.core.brain.agents import AGENTS
from nix.core.brain.events import find_project
from nix.core.brain.handoff import accept, cancel, create, listed
from nix.core.brain.profile import active, apply, forget, rebuild, review
from nix.core.brain.store import BrainStore
from nix.core.brain.worker import run_work
from nix.core.errors import ConfigError

brain_app = typer.Typer(
    help="Mega Brain: memória do projeto entre agentes. Desligado por padrão.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
hooks_app = typer.Typer(
    help="Instala, remove e mostra os hooks de captura.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
brain_app.add_typer(hooks_app, name="hooks")
handoff_app = typer.Typer(
    help="Abre, lista, reivindica e cancela o handoff do projeto.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
brain_app.add_typer(handoff_app, name="handoff")
profile_app = typer.Typer(
    help="Perfil aprendido dos projetos, sem modelo de linguagem.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
brain_app.add_typer(profile_app, name="profile")

_PRIVACY = (
    "Escopo global: os eventos de todos os repositórios desta conta podem ser gravados, "
    "incluindo caminhos e trechos de outros projetos. Confirme só se isso for aceitável."
)


def _scope(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in {"global", "project"}:
        raise ConfigError("Escopo inválido. Use `--scope global` ou `--scope project`.")
    return cleaned


def _agents(requested: list[str] | None) -> list[str]:
    return choose_agents(
        requested,
        command="nix brain hooks install",
        question=lambda key: f"Ativar {agent_hooks.spec_for(key).label}?",
    )


def _hook_exe() -> str:
    sibling = packaged_hook_executable()
    if sibling is not None:
        return agent_hooks.hook_executable(str(sibling), None)
    return agent_hooks.hook_executable(*nix_command())


def _explain_install_choices() -> None:
    """No terminal, as duas escolhas aparecem antes de qualquer gravação."""
    if not sys.stdin.isatty():
        return
    print_note(f"Você escolhe instalar um cliente, alguns ou os {len(AGENTS)} clientes.")
    print_note("Você escolhe o escopo: a conta inteira ou só o repositório.")


def _resolve_scope(scope: str | None) -> str:
    if scope is not None and scope.strip():
        return _scope(scope)
    if not sys.stdin.isatty():
        raise ConfigError(
            "Sem terminal interativo. Informe o escopo com `--scope global` ou `--scope project`."
        )
    return _scope(typer.prompt("Escopo (global ou project)"))


def _resolve_agents(agent: list[str] | None, install_all: bool) -> list[str]:
    if install_all and agent:
        raise ConfigError("Use `--all` ou `--agent`, não os dois.")
    if install_all:
        return list(agent_hooks.CONFIRMED_CLIENTS)
    if agent:
        return _agents(agent)
    if not sys.stdin.isatty():
        raise ConfigError(
            "Sem terminal interativo. Informe os clientes com `--agent` ou use "
            f"`--all` para os {len(AGENTS)}."
        )
    if typer.confirm(f"Instalar os {len(AGENTS)} clientes?", default=False):
        return list(agent_hooks.CONFIRMED_CLIENTS)
    print_note("Escolha um a um. Responda sim só para os clientes que quer ativar.")
    return _agents(None)


@brain_app.command("enable", help="Liga o Mega Brain e escolhe a wiki das páginas")
@with_errors
def cmd_enable(
    wiki: str = typer.Option(..., "--wiki", help="Wiki que recebe as páginas. Conta no limite de 100 wikis."),
) -> None:
    config = load_config()
    config.get_wiki(wiki)
    set_value("brain", "wiki", wiki.strip(), source="cli", persist=True)
    set_value("brain", "enabled", True, source="cli", persist=True)
    print_success(f"Mega Brain ligado. As páginas vão para a wiki {wiki.strip()}.")
    print_note("Ela conta no limite de 100 wikis e não pode ser removida enquanto o Mega Brain estiver ligado.")
    print_note("Para capturar, rode `nix brain hooks install --scope project` ou `--scope global`.")


@brain_app.command("status", help="Mostra se o Mega Brain está ligado e os hooks deste projeto")
@with_errors
def cmd_status(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    config = load_config()
    root, key = project_root(project)
    store = BrainStore()
    print_header("Mega Brain")
    state = "ligado" if config.brain.enabled else "desligado"
    wiki = config.brain.wiki or "nenhuma"
    print_note(f"estado: {state}; wiki: {wiki}")
    rows: list[tuple[str, str, str]] = []
    for item in agent_hooks.status(root, key, store):
        rows.append((item.spec.label, item.state, item.spec.rel_path or "sem arquivo"))
    print_table("Hooks", ("Agente", "Estado", "Arquivo"), rows)


@brain_app.command("work", hidden=True)
@with_errors
def cmd_work(
    session: str = typer.Option("", "--session", help="Sessão que disparou o trabalho."),
) -> None:
    run_work(session or None)


@hooks_app.command(
    "install",
    help=f"Ativa os hooks. No terminal, explica o escopo e se instala os {len(AGENTS)} ou um a um.",
)
@with_errors
def cmd_install(
    scope: str | None = typer.Option(
        None,
        "--scope",
        help="global (conta inteira) ou project (só o repositório).",
    ),
    agent: list[str] | None = typer.Option(None, "--agent", help=f"Agente ({', '.join(AGENTS)}). Repita para vários."),
    install_all: bool = typer.Option(
        False,
        "--all",
        help=f"Instala os {len(AGENTS)} clientes com formato confirmado: {', '.join(AGENTS)}.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Só mostra o que seria escrito"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação"),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    _explain_install_choices()
    chosen_scope = _resolve_scope(scope)
    root, key = project_root(project)
    agents = _resolve_agents(agent, install_all)
    plans = agent_hooks.plan_install(root, agents, _hook_exe(), scope=chosen_scope)
    print_header(f"hooks do Mega Brain · {chosen_scope}")
    if chosen_scope == "global":
        print_warning(_PRIVACY)
    print_plan(key, [(plan.action, _plan_path(plan), plan.spec.label) for plan in plans])
    if dry_run:
        print_note("Nada foi escrito (--dry-run).")
        return
    if not yes and not typer.confirm("Aplicar este plano?", default=False):
        print_note("Nada foi escrito.")
        raise typer.Exit(code=0)
    backups = agent_hooks.apply_install(plans, root, key, load_config().safety.backup_path, BrainStore())
    print_success("Hooks registrados.")
    for path in backups:
        print_note(f"backup: {path}")
    for plan in plans:
        if plan.spec.note:
            print_note(f"{plan.spec.label}: {plan.spec.note}")
        if plan.action == "parcial":
            print_warning(f"{plan.spec.label}: captura parcial. Nenhum arquivo de hook foi alterado.")


@profile_app.command("list", help="Lista as entradas ativas do perfil")
@with_errors
def cmd_profile_list() -> None:
    rows = [(item.category, item.page_path, item.sentence) for item in active()]
    print_table("Perfil", ("Categoria", "Página", "Frase"), rows)


@profile_app.command("forget", help="Esquece uma entrada. Ela vira lápide e não volta.")
@with_errors
def cmd_profile_forget(
    path: str = typer.Argument(..., help="Caminho, por exemplo tools/pnpm.md."),
) -> None:
    page = forget(path)
    print_success(f"Entrada esquecida: {page}. A passada seguinte não a recria.")


@profile_app.command("review", help="Mostra assuntos que ainda não têm projetos suficientes")
@with_errors
def cmd_profile_review() -> None:
    rows = [(category, focus, str(count)) for category, focus, count in review()]
    print_table("Revisão", ("Categoria", "Assunto", "Projetos"), rows)


@profile_app.command("rebuild", help="Reaprende o perfil a partir dos pedidos gravados")
@with_errors
def cmd_profile_rebuild() -> None:
    rows = rebuild()
    print_success(f"Perfil atualizado: {len(rows)} entrada(s).")


@profile_app.command("apply", help="Regrava as páginas das entradas ativas")
@with_errors
def cmd_profile_apply() -> None:
    count = apply()
    print_success(f"{count} página(s) de perfil regravadas.")


def _project_key(project: str | None) -> str:
    return find_project(project or "")[0]


@handoff_app.command("create", help="Abre o handoff do projeto")
@with_errors
def cmd_handoff_create(
    text: str = typer.Option(..., "--text", help="Onde a sessão parou."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
    session: str = typer.Option("", "--session", help="Sessão de origem, se houver."),
) -> None:
    row = create(_project_key(project), text, session)
    print_success(f"Handoff {row.id} aberto.")
    print_note("Ele continua aberto até alguém aceitar ou cancelar.")


@handoff_app.command("list", help="Lista os handoffs do projeto")
@with_errors
def cmd_handoff_list(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    rows = [
        (str(item["id"]), str(item["status"]), str(item["claimed_by"] or "—"))
        for item in listed(_project_key(project))
    ]
    print_table("Handoffs", ("Id", "Estado", "Quem reivindicou"), rows)


@handoff_app.command("accept", help="Reivindica o handoff aberto, uma única vez")
@with_errors
def cmd_handoff_accept(
    agent: str = typer.Option(..., "--agent", help="Quem está reivindicando."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    result = accept(_project_key(project), agent)
    if result.get("accepted"):
        print_success("Handoff reivindicado. O texto é histórico, não é uma ordem.")
        typer.echo(str(result.get("text") or ""))
        return
    print_warning(str(result.get("message") or "O handoff não foi reivindicado."))


@handoff_app.command("cancel", help="Cancela o handoff aberto")
@with_errors
def cmd_handoff_cancel(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    cancel(_project_key(project))
    print_success("Handoff cancelado.")


def _plan_path(plan: agent_hooks.AgentPlan) -> str:
    if plan.action == "parcial":
        return "sem arquivo"
    return plan.path.as_posix()


@hooks_app.command("remove", help="Remove os hooks do escopo pedido")
@with_errors
def cmd_remove(
    scope: str = typer.Option(..., "--scope", help="global ou project"),
    agent: list[str] | None = typer.Option(None, "--agent", help="Agente. Sem opção, pergunta um a um."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    chosen_scope = _scope(scope)
    root, key = project_root(project)
    agents = _agents(agent)
    results = agent_hooks.remove_hooks(
        root,
        agents,
        key,
        load_config().safety.backup_path,
        BrainStore(),
        scope=chosen_scope,
    )
    print_header(f"hooks do Mega Brain · {chosen_scope}")
    print_success("Hooks removidos deste escopo.")
    for result in results:
        if result.backup:
            print_note(f"backup: {result.backup}")


@hooks_app.command("status", help="Mostra os hooks do projeto e o consentimento global")
@with_errors
def cmd_hooks_status(
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    root, key = project_root(project)
    rows = [
        (item.spec.label, item.state, item.hint or item.spec.rel_path or "sem arquivo")
        for item in agent_hooks.status(root, key, BrainStore())
    ]
    print_header("hooks do Mega Brain")
    print_table("Hooks", ("Agente", "Estado", "Detalhe"), rows)
