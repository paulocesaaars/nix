"""nix wiki: cadastro delegado ao WikiService."""

from __future__ import annotations

import json

import typer
from rich.markup import escape

from nix.cli.deps import with_errors
from nix.cli.render import console, highlight, print_note, print_success, print_warning, print_wikis
from nix.config.loader import require_initialized
from nix.core.admin.wikis import WikiService

wiki_app = typer.Typer(
    help="Cadastra, renomeia, ajusta e escolhe as wikis",
    no_args_is_help=True,
)


@wiki_app.callback()
def _wiki_group(ctx: typer.Context) -> None:
    """Avisa quando a invocação usou o comando antigo `nix vault`."""
    if ctx.info_name == "vault":
        print_warning("O comando `nix vault` está obsoleto. Use `nix wiki`.")


def _service() -> WikiService:
    require_initialized()
    return WikiService()


@wiki_app.command("list")
@with_errors
def cmd_list(as_json: bool = typer.Option(False, "--json", help="Saída JSON")) -> None:
    """Lista as wikis, o caminho e qual é o padrão."""
    rows = _service().list_wikis()
    if as_json:
        payload = [
            {"name": row.name, "path": row.path, "is_default": row.is_default} for row in rows
        ]
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    if not rows:
        print_warning("Nenhuma wiki. Rode `nix init` para cadastrar a primeira.")
        return
    print_wikis(rows)


@wiki_app.command("add")
@with_errors
def cmd_add(
    name: str = typer.Argument(..., help="Nome da wiki"),
    path: str = typer.Argument(..., help="Pasta da wiki"),
) -> None:
    """Cadastra uma wiki. O primeiro vira o padrão. O limite é 100."""
    wiki = _service().add(name, path, source="cli")
    print_success(f"Wiki {highlight(wiki.name)} cadastrado em {escape(str(wiki.path))}.")
    if wiki.is_default:
        print_note("Esta é a wiki padrão.")


@wiki_app.command("rename")
@with_errors
def cmd_rename(
    old: str = typer.Argument(..., help="Nome atual"),
    new: str = typer.Argument(..., help="Nome novo"),
) -> None:
    """Troca o nome. Não move o índice nem os backups."""
    wiki = _service().rename(old, new, source="cli")
    print_success(f"Wiki renomeada para {highlight(wiki.name)}.")
    print_note(
        "O índice e os backups continuam na pasta do nome anterior. "
        f"Se a busca ficar vazia, rode `nix sync --full --wiki {escape(wiki.name)}`."
    )


@wiki_app.command("remove")
@with_errors
def cmd_remove(name: str = typer.Argument(..., help="Nome da wiki")) -> None:
    """Remove uma wiki que não seja o último nem o padrão."""
    _service().remove(name, source="cli")
    print_success(f"Wiki {highlight(name)} removido.")
    print_note("O índice em disco não foi apagado.")


@wiki_app.command("default")
@with_errors
def cmd_default(name: str = typer.Argument(..., help="Nome da wiki padrão")) -> None:
    """Define a wiki usado quando o nome é omitido."""
    wiki = _service().set_default(name, source="cli")
    print_success(f"Wiki padrão: {highlight(wiki.name)}.")


@wiki_app.command("path")
@with_errors
def cmd_path(
    name: str = typer.Argument(..., help="Nome da wiki"),
    path: str = typer.Argument(..., help="Nova pasta da wiki"),
) -> None:
    """Troca a pasta de uma wiki já cadastrado. A pasta precisa existir."""
    wiki = _service().set_path(name, path, source="cli")
    print_success(f"Wiki {highlight(wiki.name)} agora aponta para {escape(str(wiki.path))}.")
    print_note(f"Rode `nix sync --wiki {escape(wiki.name)}` para alinhar o índice.")


@wiki_app.command("set")
@with_errors
def cmd_set(
    name: str = typer.Argument(..., help="Nome da wiki"),
    key: str = typer.Argument(..., help="Ajuste: include, exclude, follow_symlinks, pastas"),
    value: str = typer.Argument(..., help="Valor. Listas e objetos entram como JSON"),
) -> None:
    """Grava um ajuste daquela wiki. Não altera a configuração global."""
    wiki, warning = _service().set_setting(name, key, value, source="cli")
    print_success(f"Ajuste gravado na wiki {highlight(wiki.name)}.")
    if warning:
        print_note(escape(warning))
