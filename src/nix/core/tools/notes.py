"""Ferramentas de escrita no vault com write-through no índice."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from nix.core.runtime import Runtime
from nix.core.vault.paths import to_posix


class CreateNoteArgs(BaseModel):
    rel_path: str = Field(description="Caminho relativo da nova nota, ex. Inbox/ideia.md")
    content: str = Field(description="Corpo Markdown da nota")
    frontmatter: dict[str, Any] | None = None


class AppendNoteArgs(BaseModel):
    rel_path: str
    content: str
    section: str | None = Field(default=None, description="Cabeçalho de seção opcional")


class UpdateNoteArgs(BaseModel):
    rel_path: str
    content: str
    mode: Literal["replace", "patch"] = "replace"
    confirm: bool = Field(
        default=False,
        description="Obrigatório true para sobrescrever (mode=replace)",
    )


class DeleteNoteArgs(BaseModel):
    rel_path: str
    confirm: bool = False


def _result_dict(result: object) -> dict[str, object]:
    from nix.core.models import WriteResult

    if isinstance(result, WriteResult):
        return {
            "rel_path": result.rel_path,
            "action": result.action,
            "chunks_indexed": result.chunks_indexed,
            "indexed": result.indexed,
            "backup_path": result.backup_path,
            "message": result.message,
        }
    raise TypeError("resultado de escrita inesperado")


def create_note(runtime: Runtime, args: CreateNoteArgs) -> dict[str, object]:
    folder = runtime.config.vault.default_new_note_folder
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
