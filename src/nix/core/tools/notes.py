"""Ferramentas de escrita no vault com write-through no índice."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from nix.core.runtime import Runtime
from nix.core.tools.args import VaultArgs
from nix.core.vault.paths import to_posix


class CreateNoteArgs(VaultArgs):
    rel_path: str = Field(description="Caminho relativo da nova nota, ex. Inbox/ideia.md")
    content: str = Field(description="Corpo Markdown da nota")
    frontmatter: dict[str, Any] | None = None


class AppendNoteArgs(VaultArgs):
    rel_path: str
    content: str
    section: str | None = Field(default=None, description="Cabeçalho de seção opcional")


class UpdateNoteArgs(VaultArgs):
    rel_path: str
    content: str
    mode: Literal["replace", "patch", "prepend"] = "replace"
    confirm: bool = Field(
        default=False,
        description="Obrigatório true para sobrescrever (mode=replace). prepend e patch não exigem.",
    )


class UpdateFrontmatterArgs(VaultArgs):
    rel_path: str
    set: dict[str, Any] | None = Field(
        default=None,
        description="Chaves de topo a gravar. Se a chave também estiver em remove, set prevalece.",
    )
    remove: list[str] | None = Field(default=None, description="Chaves de topo a apagar")


class ManageTagsArgs(VaultArgs):
    rel_path: str
    add: list[str] = Field(default_factory=list, description="Tags a acrescentar (com ou sem #)")
    remove: list[str] = Field(default_factory=list, description="Tags a remover do frontmatter")


class MoveNoteArgs(VaultArgs):
    src: str = Field(description="Caminho atual da nota .md")
    dest: str = Field(description="Novo caminho relativo no vault")
    update_links: bool = Field(
        default=True,
        description="Reescreve wikilinks e links Markdown que apontam para a nota",
    )
    overwrite: bool = False
    confirm: bool = Field(
        default=False,
        description="Obrigatório true, junto com overwrite=true, se o destino já existir",
    )


class MoveFileArgs(VaultArgs):
    src: str = Field(description="Caminho atual do anexo ou arquivo que não é nota")
    dest: str = Field(description="Novo caminho relativo no vault")
    update_links: bool = Field(
        default=True,
        description="Reescreve ![[alvo]], [[alvo]] e links Markdown relativos",
    )
    overwrite: bool = False
    confirm: bool = Field(
        default=False,
        description="Obrigatório true, junto com overwrite=true, se o destino já existir",
    )


class DeleteNoteArgs(VaultArgs):
    rel_path: str
    confirm: bool = False


def _result_dict(result: object) -> dict[str, object]:
    from nix.core.models import WriteResult

    if isinstance(result, WriteResult):
        payload: dict[str, object] = {
            "rel_path": result.rel_path,
            "action": result.action,
            "chunks_indexed": result.chunks_indexed,
            "indexed": result.indexed,
            "backup_path": result.backup_path,
            "message": result.message,
            "moved_from": result.moved_from,
            "links_updated": list(result.links_updated),
            "written": result.written,
        }
        if result.links_pending:
            payload["links_pending"] = list(result.links_pending)
        return payload
    raise TypeError("resultado de escrita inesperado")


def create_note(runtime: Runtime, args: CreateNoteArgs) -> dict[str, object]:
    folder = runtime.vault.default_new_note_folder
    rel = to_posix(args.rel_path)
    if "/" not in rel and folder:
        rel = f"{folder.rstrip('/')}/{rel}"
    written = runtime.writer.create_note(rel, args.content, args.frontmatter)
    return _result_dict(runtime.writeback.after_write(written))


def append_to_note(runtime: Runtime, args: AppendNoteArgs) -> dict[str, object]:
    written = runtime.writer.append_to_note(args.rel_path, args.content, args.section)
    return _result_dict(runtime.writeback.after_write(written))


def update_note(runtime: Runtime, args: UpdateNoteArgs) -> dict[str, object]:
    written = runtime.writer.update_note(
        args.rel_path, args.content, mode=args.mode, confirm=args.confirm
    )
    return _result_dict(runtime.writeback.after_write(written))


def delete_note(runtime: Runtime, args: DeleteNoteArgs) -> dict[str, object]:
    written = runtime.writer.delete_note(args.rel_path, confirm=args.confirm)
    return _result_dict(runtime.writeback.after_write(written))


def _unchanged(result: object) -> bool:
    from nix.core.models import WriteResult

    if not isinstance(result, WriteResult):
        return False
    return not result.written


def update_frontmatter(runtime: Runtime, args: UpdateFrontmatterArgs) -> dict[str, object]:
    written = runtime.writer.update_frontmatter(args.rel_path, args.set, args.remove)
    if _unchanged(written):
        return _result_dict(written)
    return _result_dict(runtime.writeback.after_write(written))


def manage_tags(runtime: Runtime, args: ManageTagsArgs) -> dict[str, object]:
    written = runtime.writer.manage_tags(args.rel_path, list(args.add), list(args.remove))
    if _unchanged(written):
        return _result_dict(written)
    return _result_dict(runtime.writeback.after_write(written))


def move_note(runtime: Runtime, args: MoveNoteArgs) -> dict[str, object]:
    written = runtime.writer.move_path(
        args.src,
        args.dest,
        kind="note",
        update_links=args.update_links,
        overwrite=args.overwrite,
        confirm=args.confirm,
        indexed_links=list(runtime.store.all_indexed_links()),
    )
    return _result_dict(runtime.writeback.after_move(written))


def move_file(runtime: Runtime, args: MoveFileArgs) -> dict[str, object]:
    written = runtime.writer.move_path(
        args.src,
        args.dest,
        kind="file",
        update_links=args.update_links,
        overwrite=args.overwrite,
        confirm=args.confirm,
        indexed_links=list(runtime.store.all_indexed_links()),
    )
    return _result_dict(runtime.writeback.after_move(written))
