"""Padrões da seção `sessions`, compartilhados pelo schema Pydantic e pelo hook.

O hook não carrega o Pydantic (RNF-S1), então os valores vivem aqui, num módulo
sem dependências, e os dois lados importam deste ponto único.
"""

from __future__ import annotations

import re

DEFAULT_FOLDER = "Nix/Sessões"
DEFAULT_MAX_PROMPT_BYTES = 16384
DEFAULT_MAX_TOOL_BYTES = 2048
DEFAULT_MAX_NOTE_BYTES = 65536

_DRIVE = re.compile(r"^[A-Za-z]:")


def clean_folder(value: str) -> str | None:
    """Pasta relativa ao vault, com `/` e sem bordas. `None` se for vazia, tiver `..` ou unidade."""
    cleaned = value.strip().replace("\\", "/").strip("/")
    if not cleaned or ".." in cleaned.split("/") or _DRIVE.match(cleaned):
        return None
    return cleaned
