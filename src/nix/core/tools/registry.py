"""Definição canônica das ferramentas — única fonte para o servidor MCP."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from nix.core.runtime import Runtime
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
        description="Lê o conteúdo completo de uma nota pelo caminho relativo no vault.",
        args_model=search.ReadNoteArgs,
        handler=search.read_note,
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
            "Atualiza uma nota. mode=replace é destrutivo e exige confirm=true "
            "depois que o usuário aprovar. mode=patch anexa conteúdo."
        ),
        args_model=notes.UpdateNoteArgs,
        handler=notes.update_note,
        destructive=True,
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


def _callable_from_spec(runtime: Runtime, spec: ToolSpec) -> Callable[..., str]:
    def wrapper(**kwargs: Any) -> str:
        args = spec.args_model.model_validate(kwargs)
        return _json(spec.handler(runtime, args))

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


def register_tools(server: Any, runtime: Runtime) -> None:
    annotations = None
    try:
        from mcp.types import ToolAnnotations as _ToolAnn

        annotations = _ToolAnn
    except ImportError:
        annotations = None
    for spec in SPECS:
        fn = _callable_from_spec(runtime, spec)
        kwargs: dict[str, Any] = {"name": spec.name, "description": spec.description}
        if annotations is not None:
            kwargs["annotations"] = annotations(
                destructiveHint=spec.destructive,
                readOnlyHint=spec.read_only,
                title=spec.name,
            )
        decorator = server.tool(**kwargs)
        decorator(fn)
