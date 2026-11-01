"""Remove segredos e corta trechos longos antes de qualquer gravação (RF-83 a RF-85)."""

from __future__ import annotations

import re
from collections.abc import Iterable

REDACTED = "[segredo removido]"

# Bloco inteiro de chave privada, antes dos padrões de uma linha.
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
# Cabeçalhos HTTP e pares chave=valor com nome sensível. O prefixo e o sufixo do nome têm tamanho
# limitado: sem o limite, uma sequência longa de `a-b.c-d` custava tempo quadrático (20 s em 32 KiB).
_AUTH_HEADER = re.compile(r"(?im)\b(authorization|proxy-authorization|x-api-key)\s*[:=]\s*[^\r\n]+")
_SECRET_PAIR = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]{0,32}(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"[A-Za-z0-9_.-]{0,32})(\s*[:=]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\"'}]+)"
)
# Formatos de token com prefixo conhecido.
_TOKENS = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|glpat-[A-Za-z0-9_-]{16,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")\b"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")
# Linhas de `.env` coladas no texto: NOME_EM_MAIUSCULAS=valor.
_ENV_LINE = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]{2,}=[^\r\n]+$")
_ENV_HINT = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]{2,}=")


class Sanitizer:
    """Aplica os padrões fixos e os extras da configuração."""

    def __init__(self, extra_patterns: Iterable[str] = ()) -> None:
        self._extra: list[re.Pattern[str]] = []
        for raw in extra_patterns:
            try:
                self._extra.append(re.compile(raw))
            except re.error:
                continue

    def clean(self, text: str) -> str:
        if not text:
            return text
        out = _PRIVATE_KEY.sub(REDACTED, text)
        out = _AUTH_HEADER.sub(lambda m: f"{m.group(1)}: {REDACTED}", out)
        out = _SECRET_PAIR.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
        out = _BEARER.sub(f"Bearer {REDACTED}", out)
        out = _TOKENS.sub(REDACTED, out)
        out = _redact_env_block(out)
        for pattern in self._extra:
            out = pattern.sub(REDACTED, out)
        return out


def _redact_env_block(text: str) -> str:
    """Três ou mais linhas NOME=valor seguidas parecem um `.env` e saem inteiras."""
    if len(_ENV_HINT.findall(text)) < 3:
        return text
    lines = text.splitlines()
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if len(run) >= 3:
            out.append(REDACTED + " (conteúdo de .env)")
        else:
            out.extend(run)
        run.clear()

    for line in lines:
        if _ENV_LINE.match(line):
            run.append(line)
        else:
            flush()
            out.append(line)
    flush()
    joined = "\n".join(out)
    return joined + "\n" if text.endswith("\n") else joined


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Corta em `max_bytes` sem partir um caractere UTF-8 ao meio."""
    if max_bytes <= 0:
        return ""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    marker = "…[cortado]"
    room = max(0, max_bytes - len(marker.encode("utf-8")))
    return raw[:room].decode("utf-8", errors="ignore") + marker
