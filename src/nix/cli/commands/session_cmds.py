"""nix session list | show | render."""

from __future__ import annotations

import json
import sqlite3

import typer

from nix.cli.deps import get_host, with_errors
from nix.cli.render import console
from nix.config.loader import load_config
from nix.config.schema import NixConfig
from nix.core.errors import ConfigError
from nix.core.sessions.agents import AGENT_LABELS, AGENTS
from nix.core.sessions.events import find_project
from nix.core.sessions.handoff import create_for_session, pick_source
from nix.core.sessions.render import build_note, note_rel_path, render_session
from nix.core.sessions.service import consolidate, write_note
from nix.core.sessions.store import SessionRow, SessionStore
from nix.core.tools.sessions import NO_SESSION_HINT, session_dict

session_app = typer.Typer(
    help="Sessões dos agentes gravadas pelos hooks neste projeto.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_RENDER_LIMIT = 50


def _enabled_config() -> NixConfig:
    config = load_config()
    if not config.sessions.enabled:
        raise ConfigError(
            "Os comandos de sessão estão desligados. Rode `nix config set sessions.enabled true` "
            "e, dentro do repositório, `nix hooks install` para começar a gravar."
        )
    return config


def _project(project: str | None) -> str:
    return find_project(project or "")[0]


def _find(store: SessionStore, ref: str, project: str) -> SessionRow:
    row = store.find_session(ref, project=project)
    if row is None:
        raise ConfigError(
            f"Sessão {ref!r} não encontrada no projeto {project}. Veja os ids com `nix session list`."
        )
    return row


@session_app.command("list", help="Lista as sessões do projeto atual")
@with_errors
def cmd_list(
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
    agent: str | None = typer.Option(None, "--agent", help="Filtra por agente."),
    limit: int = typer.Option(20, "--limit", min=1, max=500),
) -> None:
    _enabled_config()
    key = _project(project)
    rows = SessionStore().list_sessions(project=key, agent=agent, limit=limit)
    if as_json:
        payload = {"project": key, "sessions": [session_dict(r) for r in rows]}
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    if not rows:
        console.print(NO_SESSION_HINT)
        return
    from rich.table import Table

    table = Table(title=f"Sessões de {key}")
    for column in ("Atualizada", "Agente", "Id", "Estado", "Eventos", "Nota"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            row.updated[:16].replace("T", " "),
            AGENT_LABELS.get(row.agent, row.agent),
            row.short_id,
            row.status,
            str(row.events),
            row.note_path or "—",
        )
    console.print(table)


@session_app.command("show", help="Mostra uma sessão")
@with_errors
def cmd_show(
    ref: str = typer.Argument(..., metavar="ID", help="Id da sessão ou id curto."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
) -> None:
    config = _enabled_config()
    key = _project(project)
    store = SessionStore()
    row = _find(store, ref, key)
    rel = row.note_path or note_rel_path(config.sessions.folder, row)
    # `show` mostra a sessão inteira: o limite da nota no vault não vale aqui.
    full = config.sessions.max_note_bytes * 16
    typer.echo(build_note(row, store.events_for(row.key), note_path=rel, max_bytes=full))


@session_app.command("handoff", help="Mostra, cria ou cancela o handoff pendente do projeto")
@with_errors
def cmd_handoff(
    create: bool = typer.Option(False, "--create", help="Cria o handoff a partir da sessão mais recente."),
    cancel: bool = typer.Option(False, "--cancel", help="Cancela o handoff pendente."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help=f"Com --create, o seu agente ({', '.join(AGENTS)}): a sessão dele não vira a origem.",
    ),
) -> None:
    if create and cancel:
        raise ConfigError("Use `--create` ou `--cancel`, não os dois. Sem opção, o comando só mostra o pendente.")
    config = _enabled_config()
    key = _project(project)
    store = SessionStore()
    if cancel:
        done = store.cancel_handoff(key)
        console.print("Handoff cancelado." if done else "Não havia handoff pendente neste projeto.")
        return
    if create:
        if agent and agent not in AGENTS:
            raise ConfigError(f"Agente {agent!r} desconhecido. Use um de: {', '.join(AGENTS)}.")
        source = pick_source(store, key, agent=agent)
        if source is None:
            console.print(NO_SESSION_HINT)
            return
        created = create_for_session(store, source, config.sessions.folder)
        host = get_host()
        try:
            note, error = write_note(host, store, source.key)
        finally:
            host.close()
        console.print(f"Handoff criado a partir de {source.agent} {source.short_id}.")
        if error:
            console.print(f"[yellow]A nota não foi gravada: {error}[/yellow]")
        elif note:
            console.print(f"Nota: {note}")
        typer.echo(created.text)
        return
    pending = store.pending_handoff(key)
    if pending is None:
        if not store.list_sessions(project=key, limit=1):
            console.print(NO_SESSION_HINT)
        else:
            console.print("Não há handoff pendente. Crie um com `nix session handoff --create`.")
        return
    console.print(f"Handoff pendente (criado em {pending.created_at}, sessão {pending.session_key}):")
    typer.echo(pending.text)


@session_app.command("render", help="Grava ou atualiza a nota da sessão no vault")
@with_errors
def cmd_render(
    ref: str | None = typer.Argument(None, metavar="[ID]", help="Sessão. Sem ela, todas as do projeto."),
    project: str | None = typer.Option(None, "--project", help="Pasta do projeto. Padrão: a pasta atual."),
    drain_queue: bool = typer.Option(False, "--drain", hidden=True, help="Processa a fila do session-end."),
) -> None:
    if drain_queue:
        consolidate(load_config, get_host)
        return
    config = _enabled_config()
    key = _project(project)
    store = SessionStore()
    targets = [_find(store, ref, key)] if ref else store.list_sessions(project=key, limit=_RENDER_LIMIT)
    if not targets:
        console.print(NO_SESSION_HINT)
        return
    host = get_host()
    failures: list[str] = []
    try:
        runtime = host.resolve(config.sessions.vault or None)
        for row in targets:
            try:
                result = render_session(
                    runtime,
                    store,
                    row,
                    folder=config.sessions.folder,
                    max_bytes=config.sessions.max_note_bytes,
                )
            except Exception as exc:  # noqa: BLE001 - uma nota com erro não impede as outras
                message = getattr(exc, "message", str(exc))
                failures.append(f"{row.short_id}: {message}")
                continue
            state = "gravada" if result.written else "sem mudança"
            console.print(f"{row.short_id} ({row.agent}): {state} em {result.vault}/{result.rel_path}")
        try:
            removed = store.purge(config.sessions.retention_days)
        except sqlite3.Error as exc:
            console.print(
                f"[yellow]As notas foram gravadas, mas a retenção não rodou ({exc}). "
                "Rode `nix session render` de novo quando nenhum agente estiver gravando.[/yellow]"
            )
        else:
            if removed:
                console.print(f"[dim]{removed} eventos antigos apagados (sessions.retention_days).[/dim]")
    finally:
        host.close()
    if failures:
        raise ConfigError("Nem todas as notas foram gravadas. " + " ".join(failures))
