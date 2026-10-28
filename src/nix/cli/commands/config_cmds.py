"""nix config: lê e grava o settings.db."""

from __future__ import annotations

import json
from typing import Any

import typer

from nix.cli.deps import with_errors
from nix.cli.render import console, highlight, print_config, print_history, print_note, print_success, print_warning
from nix.config.editor import (
    history,
    revert_change,
    set_value,
    snapshot,
    split_key,
    unset_value,
)
from nix.config.loader import require_initialized
from nix.core.errors import ConfigError

config_app = typer.Typer(help="Lê e grava a configuração", no_args_is_help=True)

def _show_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


@config_app.command("list")
@with_errors
def cmd_list(
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
) -> None:
    """Lista os campos, o valor efetivo e a origem."""
    require_initialized()
    entries = snapshot()
    if as_json:
        console.print_json(json.dumps([entry.__dict__ for entry in entries], ensure_ascii=False))
        return
    print_config(entries)


@config_app.command("get")
@with_errors
def cmd_get(
    key: str = typer.Argument(..., help="Campo no formato secao.chave"),
) -> None:
    """Mostra o valor efetivo de um campo."""
    require_initialized()
    section, name = split_key(key)
    for entry in snapshot():
        if entry.section == section and entry.key == name:
            typer.echo(_show_value(entry.value))
            return
    raise ConfigError(f"Campo {section}.{name} não existe. Rode `nix config list` para ver os campos.")


@config_app.command("set")
@with_errors
def cmd_set(
    key: str = typer.Argument(..., help="Campo no formato secao.chave"),
    value: str = typer.Argument(..., help="Valor. Listas e objetos em JSON."),
) -> None:
    """Grava um campo no settings.db."""
    require_initialized()
    section, name = split_key(key)
    result = set_value(section, name, value, source="cli")
    if result.changed:
        print_success(f"{highlight(result.dotted)} atualizado.")
    else:
        print_success(f"{highlight(result.dotted)} já estava com esse valor.")
    if result.warning:
        print_warning(result.warning)


@config_app.command("unset")
@with_errors
def cmd_unset(
    key: str = typer.Argument(..., help="Campo no formato secao.chave"),
) -> None:
    """Remove o campo do settings.db e volta ao padrão."""
    require_initialized()
    section, name = split_key(key)
    result = unset_value(section, name, source="cli")
    print_success(f"{highlight(result.dotted)} voltou ao padrão.")
    if result.warning:
        print_warning(result.warning)


@config_app.command("history")
@with_errors
def cmd_history(
    limit: int = typer.Option(20, "--limit", help="Quantas alterações mostrar"),
    as_json: bool = typer.Option(False, "--json", help="Saída JSON"),
) -> None:
    """Lista alterações recentes."""
    require_initialized()
    rows = history(limit)
    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "id": row.id,
                        "field": row.dotted,
                        "old": row.old_value,
                        "new": row.new_value,
                        "source": row.source,
                        "changed_at": row.changed_at,
                    }
                    for row in rows
                ],
                ensure_ascii=False,
            )
        )
        return
    if not rows:
        print_note("Nenhuma alteração registrada.")
        return
    print_history(rows)


@config_app.command("undo")
@with_errors
def cmd_undo(
    change_id: int | None = typer.Argument(None, help="Id do histórico. Sem id, desfaz a última."),
) -> None:
    """Restaura o valor anterior de uma alteração."""
    require_initialized()
    target = change_id
    if target is None:
        rows = history(1)
        if not rows:
            raise ConfigError("Não há alterações para desfazer.")
        target = rows[0].id
    result = revert_change(target, source="cli")
    print_success(f"{highlight(result.dotted)} restaurado.")
    if result.warning:
        print_warning(result.warning)
