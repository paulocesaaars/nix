"""nix vault: cadastro delegado ao VaultService."""

from __future__ import annotations

import json

import typer

from nix.cli.deps import with_errors
from nix.cli.render import console
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
        console.print("Nenhum vault. Rode `nix init` para cadastrar o primeiro.")
        return
    for row in rows:
        mark = " [dim](padrão)[/dim]" if row.is_default else ""
        console.print(f"[cyan]{row.name}[/cyan]{mark}  {row.path}")


@vault_app.command("add")
@with_errors
def cmd_add(
    name: str = typer.Argument(..., help="Nome do vault"),
    path: str = typer.Argument(..., help="Pasta do vault do Obsidian"),
) -> None:
    """Cadastra um vault. O primeiro vira o padrão. O limite é 5."""
    vault = _service().add(name, path, source="cli")
    console.print(f"Vault [cyan]{vault.name}[/cyan] cadastrado em {vault.path}.")
    if vault.is_default:
        console.print("Este é o vault padrão.")


@vault_app.command("rename")
@with_errors
def cmd_rename(
    old: str = typer.Argument(..., help="Nome atual"),
    new: str = typer.Argument(..., help="Nome novo"),
) -> None:
    """Troca o nome. Não move o índice nem os backups."""
    vault = _service().rename(old, new, source="cli")
    console.print(f"Vault renomeado para [cyan]{vault.name}[/cyan].")
    console.print(
        "[dim]O índice e os backups continuam na pasta do nome anterior. "
        f"Se a busca ficar vazia, rode `nix sync --full --vault {vault.name}`.[/dim]"
    )


@vault_app.command("remove")
@with_errors
def cmd_remove(name: str = typer.Argument(..., help="Nome do vault")) -> None:
    """Remove um vault que não seja o último nem o padrão."""
    _service().remove(name, source="cli")
    console.print(f"Vault [cyan]{name}[/cyan] removido. O índice em disco não foi apagado.")


@vault_app.command("default")
@with_errors
def cmd_default(name: str = typer.Argument(..., help="Nome do vault padrão")) -> None:
    """Define o vault usado quando o nome é omitido."""
    vault = _service().set_default(name, source="cli")
    console.print(f"Vault padrão: [cyan]{vault.name}[/cyan].")


@vault_app.command("path")
@with_errors
def cmd_path(
    name: str = typer.Argument(..., help="Nome do vault"),
    path: str = typer.Argument(..., help="Nova pasta do vault do Obsidian"),
) -> None:
    """Troca a pasta de um vault já cadastrado. A pasta precisa existir."""
    vault = _service().set_path(name, path, source="cli")
    console.print(f"Vault [cyan]{vault.name}[/cyan] agora aponta para {vault.path}.")
    console.print(f"[dim]Rode `nix sync --vault {vault.name}` para alinhar o índice.[/dim]")


@vault_app.command("set")
@with_errors
def cmd_set(
    name: str = typer.Argument(..., help="Nome do vault"),
    key: str = typer.Argument(..., help="Ajuste: include, exclude, follow_symlinks, pastas"),
    value: str = typer.Argument(..., help="Valor. Listas e objetos entram como JSON"),
) -> None:
    """Grava um ajuste daquele vault. Não altera a configuração global."""
    vault, warning = _service().set_setting(name, key, value, source="cli")
    console.print(f"Ajuste gravado no vault [cyan]{vault.name}[/cyan].")
    if warning:
        console.print(f"[dim]{warning}[/dim]")
