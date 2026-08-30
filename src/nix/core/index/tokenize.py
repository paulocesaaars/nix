"""Contagem de tokens para o chunker.

Prefere `tiktoken` (`cl100k_base`). Se a extensão nativa não carregar —
comum no Windows com Python 3.14 e Controle de Aplicativo — usa ~4
caracteres por token, a mesma ordem de grandeza do cl100k.
"""

from __future__ import annotations

from typing import Any

from nix.observability.logging import get_logger

logger = get_logger("nix.index.tokenize")

_CHARS_PER_TOKEN = 4

APPROXIMATE_TOKENIZER_HINT = (
    "Contagem de tokens aproximada (~4 caracteres por token): o tiktoken não "
    "carregou. No Windows, o Controle de Aplicativo pode bloquear o .pyd no "
    "Python 3.14 — permita o arquivo em .venv/Lib/site-packages na Segurança "
    "do Windows ou recrie o ambiente. O tamanho dos chunks pode divergir de "
    "uma máquina com tiktoken."
)


class TokenCounter:
    """Conta e recorta tokens com tiktoken, ou por aproximação."""

    def __init__(self) -> None:
        self._encoding: Any | None = None
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError as exc:
            logger.warning("%s (%s)", APPROXIMATE_TOKENIZER_HINT, exc)

    @property
    def approximate(self) -> bool:
        return self._encoding is None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)

    def tail(self, text: str, overlap_tokens: int) -> str:
        if overlap_tokens <= 0 or not text:
            return ""
        if self._encoding is not None:
            tokens = self._encoding.encode(text)
            if len(tokens) <= overlap_tokens:
                return text
            return str(self._encoding.decode(tokens[-overlap_tokens:])).strip()
        chars = overlap_tokens * _CHARS_PER_TOKEN
        if chars >= len(text):
            return text
        return text[-chars:].strip()
