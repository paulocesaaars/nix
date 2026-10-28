"""nix vault: cadastro delegado ao VaultService."""

from __future__ import annotations

import json

import typer
from rich.markup import escape

from nix.cli.deps import with_errors
from nix.cli.render import console, highlight, print_note, print_success, print_vaults, print_warning
from nix.config.loader import require_initialized
from nix.core.admin.vaults import VaultService

vault_app = typer.Typer(
    help="Cadastra, renomeia, ajusta e escolhe os vaults",
    no_args_is_help=True,
)


def _service() -> VaultService:
    require_initialized()
    return VaultService()


@vault_app.command("list")
@with_errors
def cmd_list(as_json: bool = typer.Option(False, "--json", help="Saída JSON")) -> None:
    """Lista os vaults, o caminho e qual é o padrão."""
    rows = _service().list_vaults()
    if as_json:
        payload = [
            {"name": row.name, "path": row.path, "is_default": row.is_default} for row in rows
        ]
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    if not rows:
        print_warning("Nenhum vault. Rode `nix init` para cadastrar o primeiro.")
        return
    print_vaults(rows)


@vault_app.command("add")
@with_errors
def cmd_add(
    name: str = typer.Argument(..., help="Nome do vault"),
    path: str = typer.Argument(..., help="Pasta do vault do Obsidian"),
) -> None:
    """Cadastra um vault. O primeiro vira o padrão. O limite é 5."""
    vault = _service().add(name, path, source="cli")
    print_success(f"Vault {highlight(vault.name)} cadastrado em {escape(str(vault.path))}.")
    if vault.is_default:
        print_note("Este é o vault padrão.")


@vault_app.command("rename")
@with_errors
def cmd_rename(
    old: str = typer.Argument(..., help="Nome atual"),
    new: str = typer.Argument(..., help="Nome novo"),
) -> None:
    """Troca o nome. Não move o índice nem os backups."""
    vault = _service().rename(old, new, source="cli")
    print_success(f"Vault renomeado para {highlight(vault.name)}.")
    print_note(
        "O índice e os backups continuam na pasta do nome anterior. "
        f"Se a busca ficar vazia, rode `nix sync --full --vault {escape(vault.name)}`."
    )


@vault_app.command("remove")
@with_errors
def cmd_remove(name: str = typer.Argument(..., help="Nome do vault")) -> None:
    """Remove um vault que não seja o último nem o padrão."""
    _service().remove(name, source="cli")
    print_success(f"Vault {highlight(name)} removido.")
    print_note("O índice em disco não foi apagado.")


@vault_app.command("default")
@with_errors
def cmd_default(name: str = typer.Argument(..., help="Nome do vault padrão")) -> None:
    """Define o vault usado quando o nome é omitido."""
    vault = _service().set_default(name, source="cli")
    print_success(f"Vault padrão: {highlight(vault.name)}.")


@vault_app.command("path")
@with_errors
def cmd_path(
    name: str = typer.Argument(..., help="Nome do vault"),
    path: str = typer.Argument(..., help="Nova pasta do vault do Obsidian"),
) -> None:
    """Troca a pasta de um vault já cadastrado. A pasta precisa existir."""
    vault = _service().set_path(name, path, source="cli")
    print_success(f"Vault {highlight(vault.name)} agora aponta para {escape(str(vault.path))}.")
    print_note(f"Rode `nix sync --vault {escape(vault.name)}` para alinhar o índice.")


@vault_app.command("set")
@with_errors
def cmd_set(
    name: str = typer.Argument(..., help="Nome do vault"),
    key: str = typer.Argument(..., help="Ajuste: include, exclude, follow_symlinks, pastas"),
    value: str = typer.Argument(..., help="Valor. Listas e objetos entram como JSON"),
) -> None:
    """Grava um ajuste daquele vault. Não altera a configuração global."""
    vault, warning = _service().set_setting(name, key, value, source="cli")
    print_success(f"Ajuste gravado no vault {highlight(vault.name)}.")
    if warning:
        print_note(escape(warning))
