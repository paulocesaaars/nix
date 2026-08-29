"""Contorna extensões nativas bloqueadas pelo Windows (Controle de Aplicativo)."""

from __future__ import annotations

import sys
import types
import zlib


def allow_blocked_mmh3() -> None:
    """Garante `import mmh3` para o FastEmbed.

    O `__init__` do FastEmbed importa BM25/sparse e exige `mmh3`, mesmo quando
    só usamos embeddings densos. No Windows com Python 3.14 o Controle de
    Aplicativo pode bloquear o `.pyd`. O stub só desbloqueia o import; o Nix
    não usa BM25.
    """
    try:
        import mmh3  # noqa: F401
        return
    except ImportError:
        sys.modules.pop("mmh3", None)

    stub = types.ModuleType("mmh3")

    def hash(key: str | bytes, seed: int = 0, signed: bool = True) -> int:  # noqa: A001
        data = key.encode("utf-8") if isinstance(key, str) else key
        value = zlib.crc32(data, seed) & 0xFFFFFFFF
        if signed and value >= 0x80000000:
            value -= 0x100000000
        return value

    stub.hash = hash  # type: ignore[attr-defined]
    sys.modules["mmh3"] = stub
