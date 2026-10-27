"""Parâmetro `vault` compartilhado pelas ferramentas MCP."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VaultArgs(BaseModel):
    """Escrita e leitura de uma nota: um único nome, ou o vault padrão."""

    vault: str | None = Field(
        default=None,
        description=(
            "Nome de um único vault. Omita para usar o padrão. "
            'A comparação ignora maiúsculas. Lista ou "*" não é aceito: informe um nome só.'
        ),
    )


class MultiVaultArgs(BaseModel):
    """Busca, listas e sincronização: um nome, uma lista ou todos."""

    vault: str | list[str] | None = Field(
        default=None,
        description=(
            'Nome, lista de nomes ou "*" para todos os vaults. '
            "Omita para usar o padrão. A comparação ignora maiúsculas."
        ),
    )
