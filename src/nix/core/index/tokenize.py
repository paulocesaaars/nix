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

def approximate_tokenizer_hint() -> str:
    """Aviso quando o tiktoken não carrega e a contagem vira aproximação."""
    from nix.core.index.native_compat import native_extension_remedy

    return (
        "Contagem de tokens aproximada (~4 caracteres por token): o tiktoken não "
        "carregou. No Windows, o Controle de Aplicativo pode bloquear a extensão nativa. "
        f"{native_extension_remedy()} O tamanho dos chunks pode divergir de "
        "uma máquina com tiktoken."
    )


class TokenCounter:
    """Conta e recorta tokens com tiktoken, ou por aproximação."""

    def __init__(self) -> None:
        self._encoding: Any | None = None
        try:
            import tiktoken
            from tiktoken_ext.openai_public import cl100k_base  # type: ignore[import-untyped]

            # get_encoding varre tiktoken_ext com pkgutil. No binário Nuitka
            # esse namespace não lista módulos, e o cl100k_base some.
            self._encoding = tiktoken.Encoding(**cl100k_base())
        except ImportError as exc:
            logger.warning("%s (%s)", approximate_tokenizer_hint(), exc)

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
