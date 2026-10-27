"""Definição canônica das ferramentas — única fonte para o servidor MCP."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from nix.core.errors import ConfigError
from nix.core.runtime import RuntimeHost, VaultOpenError
from nix.core.tools import maintenance, notes, search

_SINGLE_VAULT = (
    "Esta operação usa um único vault. Informe um nome só, ou omita para usar o padrão. "
    "Veja os nomes com `nix vault list`."
)
_VAULT_ONE = ' Parâmetro vault: um nome; omita para o vault padrão. Lista ou "*" é recusado.'
_VAULT_MANY = ' Parâmetro vault: um nome, uma lista ou "*" para todos; omita para o vault padrão.'


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., Any]
    destructive: bool = False
    read_only: bool = True
    multi_vault: bool = False


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_notes",
        description=(
            "Busca trechos relevantes no vault (híbrida: semântica + léxica). "
            "Use para responder perguntas sobre as notas. Filtros opcionais: pasta, tags, datas."
            + _VAULT_MANY
        ),
        args_model=search.SearchNotesArgs,
        handler=search.search_notes,
        read_only=True,
        multi_vault=True,
    ),
    ToolSpec(
        name="read_note",
        description=(
            "Lê o conteúdo completo de uma nota pelo caminho relativo no vault. "
            "Em notas longas, prefira get_note_outline e read_note_lines."
            + _VAULT_ONE
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
            + _VAULT_ONE
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
            + _VAULT_ONE
        ),
        args_model=search.ReadNoteLinesArgs,
        handler=search.read_note_lines,
        read_only=True,
    ),
    ToolSpec(
        name="list_notes",
        description="Lista notas indexadas, com filtro opcional por pasta ou tag." + _VAULT_MANY,
        args_model=search.ListNotesArgs,
        handler=search.list_notes,
        read_only=True,
        multi_vault=True,
    ),
    ToolSpec(
        name="list_all_tags",
        description=(
            "Lista as tags indexadas com a contagem de notas, da mais frequente para a menos frequente. "
            "A saída alimenta o filtro tag de search_notes e list_notes. "
            "As contagens são a soma dos vaults pedidos, com o detalhe em vaults."
            + _VAULT_MANY
        ),
        args_model=search.ListAllTagsArgs,
        handler=search.list_all_tags,
        read_only=True,
        multi_vault=True,
    ),
    ToolSpec(
        name="get_linked_notes",
        description="Navega wikilinks de uma nota (outgoing, incoming ou both)." + _VAULT_ONE,
        args_model=search.LinkedNotesArgs,
        handler=search.get_linked_notes,
        read_only=True,
    ),
    ToolSpec(
        name="create_note",
        description=(
            "Cria uma nota Markdown no vault e indexa imediatamente (write-through). "
            "Se o caminho não tiver pasta, usa vault.default_new_note_folder."
            + _VAULT_ONE
        ),
        args_model=notes.CreateNoteArgs,
        handler=notes.create_note,
        read_only=False,
    ),
    ToolSpec(
        name="append_to_note",
        description="Anexa conteúdo a uma nota existente e reindexa o arquivo." + _VAULT_ONE,
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
            + _VAULT_ONE
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
            + _VAULT_ONE
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
            + _VAULT_ONE
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
            + _VAULT_ONE
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
            + _VAULT_ONE
        ),
        args_model=notes.MoveFileArgs,
        handler=notes.move_file,
        destructive=False,
        read_only=False,
    ),
    ToolSpec(
        name="delete_note",
        description="Remove uma nota do vault e do índice. Destrutivo: exige confirm=true." + _VAULT_ONE,
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
            "Use quando o usuário pedir ou quando index_status indicar defasagem. "
            "Vários vaults rodam em sequência, com um relatório por vault."
            + _VAULT_MANY
        ),
        args_model=maintenance.SyncIndexArgs,
        handler=maintenance.sync_index,
        read_only=False,
        multi_vault=True,
    ),
    ToolSpec(
        name="index_status",
        description=(
            "Retorna contagens do índice, último sync e se está desatualizado, por vault."
            + _VAULT_MANY
        ),
        args_model=maintenance.IndexStatusArgs,
        handler=maintenance.index_status,
        read_only=True,
        multi_vault=True,
    ),
    ToolSpec(
        name="vault_insights",
        description=(
            "Qualidade do vault: kind=orphans|duplicates|links|summary. "
            "Órfãs, títulos duplicados, sugestão de wikilinks ou resumo."
            + _VAULT_ONE
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
            + _VAULT_ONE
        ),
        args_model=maintenance.RememberArgs,
        handler=maintenance.remember,
        read_only=False,
    ),
    ToolSpec(
        name="list_vaults",
        description=(
            "Lista os vaults cadastrados: nome, caminho, se é o padrão e se o índice está desatualizado. "
            "Somente leitura. Não escolhe vault: devolve todos."
        ),
        args_model=maintenance.ListVaultsArgs,
        handler=maintenance.list_vaults,
        read_only=True,
        multi_vault=True,
    ),
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def call_tool(host: RuntimeHost, name: str, payload: dict[str, Any]) -> Any:
    for spec in SPECS:
        if spec.name == name:
            if not spec.multi_vault:
                _reject_multi_vault(payload.get("vault"))
            args = spec.args_model.model_validate(payload)
            return _dispatch(host, spec, args)
    raise KeyError(
        f"Ferramenta {name!r} desconhecida. Ferramentas: {', '.join(s.name for s in SPECS)}."
    )


def _reject_multi_vault(value: object) -> None:
    if isinstance(value, list) or (isinstance(value, str) and value.strip() == "*"):
        raise ConfigError(_SINGLE_VAULT)


def _dispatch(host: RuntimeHost, spec: ToolSpec, args: Any) -> Any:
    if spec.multi_vault:
        spec_value = getattr(args, "vault", "*") if "vault" in spec.args_model.model_fields else "*"
        opened = host.resolve_many(spec_value)
        payload = spec.handler(opened.runtimes, args)
        return _attach_open_errors(spec.name, payload, opened.errors)
    raw = getattr(args, "vault", None)
    _reject_multi_vault(raw)
    name = raw.strip() if isinstance(raw, str) and raw.strip() else None
    runtime = host.resolve(name)
    return _stamp_vault(spec.handler(runtime, args), runtime.vault.name)


def _attach_open_errors(tool: str, payload: Any, errors: list[VaultOpenError]) -> Any:
    """Junta a falha de abrir um vault cadastrado ao resultado. Os outros já foram atendidos."""
    if not errors:
        return payload
    rows = [{"vault": item.name, "message": item.message} for item in errors]
    if not isinstance(payload, dict):
        return {"result": payload, "vault_errors": rows}
    names = _string_list(payload.get("vault"))
    names.extend(item.name for item in errors)
    if tool == "sync_index":
        reports = _dict_list(payload.get("reports"))
        reports.extend({"vault": item.name, "error": item.message} for item in errors)
        return {**payload, "vault": names, "reports": reports}
    if tool == "index_status":
        vaults = _dict_list(payload.get("vaults"))
        for item in errors:
            vaults.append(
                {
                    "vault": item.name,
                    "error": item.message,
                    "files": 0,
                    "chunks": 0,
                    "errors": 0,
                    "last_sync_at": None,
                    "embedding_model": None,
                    "vault_path": item.path,
                    "stale": True,
                    "stale_reason": item.message,
                    "data_dir": "",
                }
            )
        return {**payload, "vault": names, "vaults": vaults}
    if tool == "list_vaults":
        vaults = _dict_list(payload.get("vaults"))
        for item in errors:
            vaults.append(
                {
                    "vault": item.name,
                    "name": item.name,
                    "path": item.path,
                    "is_default": item.is_default,
                    "stale": True,
                    "error": item.message,
                }
            )
        return {**payload, "vault": names, "vaults": vaults}
    current = payload.get("vault_errors")
    merged = list(current) if isinstance(current, list) else []
    merged.extend(rows)
    return {**payload, "vault": names, "vault_errors": merged}


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _stamp_vault(payload: Any, vault_name: str) -> Any:
    if isinstance(payload, dict):
        if "vault" in payload:
            return payload
        return {**payload, "vault": vault_name}
    if isinstance(payload, list):
        stamped: list[Any] = []
        for item in payload:
            if isinstance(item, dict) and "vault" not in item:
                stamped.append({**item, "vault": vault_name})
            else:
                stamped.append(item)
        return stamped
    return {"vault": vault_name, "result": payload}


def _attach_warning(payload: Any, warning: str) -> Any:
    if isinstance(payload, dict):
        return {**payload, "config_warning": warning}
    return {"result": payload, "config_warning": warning}


def _callable_from_spec(host: RuntimeHost, spec: ToolSpec) -> Callable[..., str]:
    def wrapper(**kwargs: Any) -> str:
        warning = host.before_call()
        if not spec.multi_vault:
            _reject_multi_vault(kwargs.get("vault"))
        args = spec.args_model.model_validate(kwargs)
        payload = _dispatch(host, spec, args)
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
