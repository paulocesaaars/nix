"""Definição canônica das ferramentas — única fonte para o servidor MCP."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from nix.core.runtime import Runtime, RuntimeHost
from nix.core.tools import maintenance, notes, search


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Runtime, Any], Any]
    destructive: bool = False
    read_only: bool = True


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_notes",
        description=(
            "Busca trechos relevantes no vault (híbrida: semântica + léxica). "
            "Use para responder perguntas sobre as notas. Filtros opcionais: pasta, tags, datas."
        ),
        args_model=search.SearchNotesArgs,
        handler=search.search_notes,
        read_only=True,
    ),
    ToolSpec(
        name="read_note",
        description=(
            "Lê o conteúdo completo de uma nota pelo caminho relativo no vault. "
            "Em notas longas, prefira get_note_outline e read_note_lines."
        ),
        args_model=search.ReadNoteArgs,
        handler=search.read_note,
        read_only=True,
    ),
    ToolSpec(
        name="get_note_outline",
        description=(
            "Devolve título, chaves do frontmatter, total de linhas e headings "
            "(level, title, path, start_line, end_line no arquivo, começando em 1). "
            "Use antes de read_note_lines. Prefira este par a read_note em notas longas."
        ),
        args_model=search.GetNoteOutlineArgs,
        handler=search.get_note_outline,
        read_only=True,
    ),
    ToolSpec(
        name="read_note_lines",
        description=(
            "Lê um intervalo de linhas do arquivo (1 = primeira linha, frontmatter incluído) "
            'ou um heading ("Seção" ou "Pai > Filho"). Limite de 400 linhas; '
            "a resposta traz truncated e next_start_line. "
            "start_line de search_notes e de get_note_outline servem direto aqui. "
            "Prefira get_note_outline + read_note_lines a read_note em notas longas."
        ),
        args_model=search.ReadNoteLinesArgs,
        handler=search.read_note_lines,
        read_only=True,
    ),
    ToolSpec(
        name="list_notes",
        description="Lista notas indexadas, com filtro opcional por pasta ou tag.",
        args_model=search.ListNotesArgs,
        handler=search.list_notes,
        read_only=True,
    ),
    ToolSpec(
        name="list_all_tags",
        description=(
            "Lista as tags indexadas com a contagem de notas, da mais frequente para a menos frequente. "
            "A saída alimenta o filtro tag de search_notes e list_notes."
        ),
        args_model=search.ListAllTagsArgs,
        handler=search.list_all_tags,
        read_only=True,
    ),
    ToolSpec(
        name="get_linked_notes",
        description="Navega wikilinks de uma nota (outgoing, incoming ou both).",
        args_model=search.LinkedNotesArgs,
        handler=search.get_linked_notes,
        read_only=True,
    ),
    ToolSpec(
        name="create_note",
        description=(
            "Cria uma nota Markdown no vault e indexa imediatamente (write-through). "
            "Se o caminho não tiver pasta, usa vault.default_new_note_folder."
        ),
        args_model=notes.CreateNoteArgs,
        handler=notes.create_note,
        read_only=False,
    ),
    ToolSpec(
        name="append_to_note",
        description="Anexa conteúdo a uma nota existente e reindexa o arquivo.",
        args_model=notes.AppendNoteArgs,
        handler=notes.append_to_note,
        read_only=False,
    ),
    ToolSpec(
        name="update_note",
        description=(
            "Atualiza uma nota e reindexa. mode=replace substitui o arquivo inteiro, "
            "é destrutivo e exige confirm=true. mode=patch anexa conteúdo. "
            "mode=prepend insere o texto depois do frontmatter (o YAML original fica intacto) "
            "e antes do corpo, sem confirm."
        ),
        args_model=notes.UpdateNoteArgs,
        handler=notes.update_note,
        destructive=True,
        read_only=False,
    ),
    ToolSpec(
        name="update_frontmatter",
        description=(
            "Altera chaves de topo do frontmatter YAML sem reformatar o resto do bloco "
            "(comentários, ordem e aspas das outras chaves permanecem). "
            "set grava valores; remove apaga chaves. Se a chave estiver nos dois, set prevalece. "
            "Reindexa a nota (write-through)."
        ),
        args_model=notes.UpdateFrontmatterArgs,
        handler=notes.update_frontmatter,
        read_only=False,
    ),
    ToolSpec(
        name="manage_tags",
        description=(
            "Adiciona ou remove tags do frontmatter. Aceita lista ou string, ignora #, "
            "remove duplicatas e preserva a ordem. Não altera tags inline do corpo; "
            "a resposta lista as que ficaram. Reindexa a nota (write-through)."
        ),
        args_model=notes.ManageTagsArgs,
        handler=notes.manage_tags,
        read_only=False,
    ),
    ToolSpec(
        name="move_note",
        description=(
            "Move ou renomeia uma nota .md dentro do vault. Por padrão (update_links=true) "
            "reescreve [[alvo]], [[alvo|alias]], [[alvo#heading]], ![[alvo]] e links Markdown "
            "relativos nas notas que apontam para ela. Cada nota alterada ganha backup. "
            "Links pelo título do frontmatter não mudam se o título não mudou. "
            "Notas fora de include/exclude ficam em links_pending e não são alteradas. "
            "Destino existente exige overwrite=true e confirm=true. Para anexos, use move_file."
        ),
        args_model=notes.MoveNoteArgs,
        handler=notes.move_note,
        destructive=False,
        read_only=False,
    ),
    ToolSpec(
        name="move_file",
        description=(
            "Move um anexo ou outro arquivo que não é nota (PDF, imagem etc.). "
            "Recusa .md: use move_note. Atualiza ![[alvo]], [[alvo]] e links Markdown relativos "
            "pelo caminho ou nome do arquivo. Destino existente exige overwrite=true e confirm=true. "
            "O anexo só volta ao índice se index.index_attachments estiver ativo (vale para PDF)."
        ),
        args_model=notes.MoveFileArgs,
        handler=notes.move_file,
        destructive=False,
        read_only=False,
    ),
    ToolSpec(
        name="delete_note",
        description="Remove uma nota do vault e do índice. Destrutivo: exige confirm=true.",
        args_model=notes.DeleteNoteArgs,
        handler=notes.delete_note,
        destructive=True,
        read_only=False,
    ),
    ToolSpec(
        name="sync_index",
        description=(
            "Sincroniza o índice com o vault. Incremental por padrão. "
            "full=true reconstrói tudo; dry_run=true só pré-visualiza. "
            "Use quando o usuário pedir ou quando index_status indicar defasagem."
        ),
        args_model=maintenance.SyncIndexArgs,
        handler=maintenance.sync_index,
        read_only=False,
    ),
    ToolSpec(
        name="index_status",
        description="Retorna contagens do índice, último sync e se está desatualizado.",
        args_model=maintenance.IndexStatusArgs,
        handler=maintenance.index_status,
        read_only=True,
    ),
    ToolSpec(
        name="vault_insights",
        description=(
            "Qualidade do vault: kind=orphans|duplicates|links|summary. "
            "Órfãs, títulos duplicados, sugestão de wikilinks ou resumo."
        ),
        args_model=maintenance.InsightsArgs,
        handler=maintenance.vault_insights,
        read_only=True,
    ),
    ToolSpec(
        name="remember",
        description=(
            "Persiste um fato duradouro como nota em vault.longterm_folder. "
            "Use para preferências e decisões que devem sobreviver à sessão."
        ),
        args_model=maintenance.RememberArgs,
        handler=maintenance.remember,
        read_only=False,
    ),
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def call_tool(runtime: Runtime, name: str, payload: dict[str, Any]) -> Any:
    for spec in SPECS:
        if spec.name == name:
            args = spec.args_model.model_validate(payload)
            return spec.handler(runtime, args)
    raise KeyError(
        f"Ferramenta {name!r} desconhecida. Ferramentas: {', '.join(s.name for s in SPECS)}."
    )


def _attach_warning(payload: Any, warning: str) -> Any:
    if isinstance(payload, dict):
        return {**payload, "config_warning": warning}
    return {"result": payload, "config_warning": warning}


def _callable_from_spec(host: RuntimeHost, spec: ToolSpec) -> Callable[..., str]:
    def wrapper(**kwargs: Any) -> str:
        warning = host.before_call()
        args = spec.args_model.model_validate(kwargs)
        payload = spec.handler(host.runtime, args)
        if warning:
            payload = _attach_warning(payload, warning)
        return _json(payload)

    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": str}
    for field_name, field in spec.args_model.model_fields.items():
        default = inspect.Parameter.empty if field.is_required() else field.default
        if default is None or (default is not inspect.Parameter.empty and default is field.default):
            default = field.default if not field.is_required() else inspect.Parameter.empty
        annotation = field.annotation
        annotations[field_name] = annotation
        params.append(
            inspect.Parameter(
                field_name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
    wrapper.__name__ = spec.name
    wrapper.__doc__ = spec.description
    wrapper.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    wrapper.__annotations__ = annotations
    return wrapper


def register_tools(server: Any, host: RuntimeHost) -> None:
    annotations = None
    try:
        from mcp.types import ToolAnnotations as _ToolAnn

        annotations = _ToolAnn
    except ImportError:
        annotations = None
    for spec in SPECS:
        fn = _callable_from_spec(host, spec)
        kwargs: dict[str, Any] = {"name": spec.name, "description": spec.description}
        if annotations is not None:
            kwargs["annotations"] = annotations(
                destructiveHint=spec.destructive,
                readOnlyHint=spec.read_only,
                title=spec.name,
            )
        decorator = server.tool(**kwargs)
        decorator(fn)
