"""Parâmetro `wiki` compartilhado pelas ferramentas MCP."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WikiArgs(BaseModel):
    """Escrita e leitura de uma nota: um único nome, ou a wiki padrão."""

    wiki: str | None = Field(
        default=None,
        description=(
            "Nome de uma única wiki. Omita para usar o padrão. "
            'A comparação ignora maiúsculas. Lista ou "*" não é aceito: informe um nome só.'
        ),
    )


class MultiWikiArgs(BaseModel):
    """Busca, listas e sincronização: um nome, uma lista ou todos."""

    wiki: str | list[str] | None = Field(
        default=None,
        description=(
            'Nome, lista de nomes ou "*" para todas as wikis. '
            "Omita para usar o padrão. A comparação ignora maiúsculas."
        ),
    )
