"""Parâmetro `wiki` compartilhado pelas ferramentas MCP.

O parâmetro `vault` continua aceito por uma versão e a resposta avisa para usar `wiki`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

LEGACY_WIKI_PARAM = "vault"
LEGACY_WIKI_PARAM_WARNING = "O parâmetro vault está obsoleto. Use o parâmetro wiki."


def _copy_legacy_wiki(data: Any) -> Any:
    """Copia `vault` para `wiki` quando o nome novo não veio. O antigo permanece para o aviso."""
    if not isinstance(data, dict) or LEGACY_WIKI_PARAM not in data:
        return data
    copied = dict(data)
    current = copied.get("wiki")
    if current in (None, "", []):
        copied["wiki"] = copied[LEGACY_WIKI_PARAM]
    return copied


class WikiArgs(BaseModel):
    """Escrita e leitura de uma nota: um único nome, ou a wiki padrão."""

    wiki: str | None = Field(
        default=None,
        description=(
            "Nome de uma única wiki. Omita para usar o padrão. "
            'A comparação ignora maiúsculas. Lista ou "*" não é aceito: informe um nome só.'
        ),
    )
    vault: str | None = Field(
        default=None,
        description="Obsoleto. Use wiki. Ainda devolve o resultado e avisa para trocar o nome.",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_vault(cls, data: Any) -> Any:
        return _copy_legacy_wiki(data)


class MultiWikiArgs(BaseModel):
    """Busca, listas e sincronização: um nome, uma lista ou todos."""

    wiki: str | list[str] | None = Field(
        default=None,
        description=(
            'Nome, lista de nomes ou "*" para todas as wikis. '
            "Omita para usar o padrão. A comparação ignora maiúsculas."
        ),
    )
    vault: str | list[str] | None = Field(
        default=None,
        description="Obsoleto. Use wiki. Ainda devolve o resultado e avisa para trocar o nome.",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_vault(cls, data: Any) -> Any:
        return _copy_legacy_wiki(data)


def used_legacy_wiki_param(args: BaseModel) -> bool:
    legacy = getattr(args, "vault", None)
    return legacy not in (None, "", [])
