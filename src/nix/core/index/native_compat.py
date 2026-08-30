"""Contorna extensões nativas bloqueadas pelo Windows (Controle de Aplicativo).

Chame `prepare_native_imports` uma vez na subida do `Runtime`, antes de
importar Chroma ou FastEmbed.
"""

from __future__ import annotations

import sys
import types
import zlib

from nix.core.errors import ConfigError

_PREPARED = False
_MMH3_IS_STUB = False
_OTEL_GRPC_STUB = False

_CHROMA_MMH3_HINT = (
    "O ChromaDB precisou de mmh3.hash, mas a extensão nativa não carregou "
    "(comum no Windows com Python 3.14 e Controle de Aplicativo). "
    "Permita o arquivo .pyd em .venv/Lib/site-packages na Segurança do Windows "
    "ou recrie o ambiente com um Python em que o mmh3 carregue (ex.: 3.12)."
)

_CYGRPC_HINT = (
    "O Windows bloqueou uma extensão nativa (.pyd) do Chroma (Controle de "
    "Aplicativo, comum no Python 3.14). O cliente local usa RustBindingsAPI e "
    "não precisa de gRPC. Permita os .pyd em .venv/Lib/site-packages "
    "(grpc/_cython e chromadb*) na Segurança do Windows ou recrie o ambiente "
    "com Python 3.12."
)

_OTEL_STUB_FAILED_HINT = (
    "O Nix não liga telemetria do Chroma. O contorno do exporter OTLP falhou. "
    "Permita o .pyd cygrpc em .venv/Lib/site-packages/grpc/_cython ou recrie o "
    "ambiente com Python 3.12."
)


def mmh3_is_stub() -> bool:
    return _MMH3_IS_STUB


def otel_grpc_is_stub() -> bool:
    return _OTEL_GRPC_STUB


def is_blocked_native_dll(exc: BaseException) -> bool:
    text = str(exc)
    return (
        "cygrpc" in text
        or "Controle de Aplicativo" in text
        or "Application Control" in text
        or "DLL load failed" in text
    )


def blocked_native_hint() -> str:
    return _CYGRPC_HINT


def prepare_native_imports() -> None:
    """Prepara imports nativos que o Windows 3.14 costuma bloquear.

    - `mmh3`: o FastEmbed importa BM25/sparse mesmo para embeddings densos.
      O stub só desbloqueia o import; se o Chroma chamar `hash()`, falha.
    - exporter OTLP gRPC: o Chroma 1.x importa `OTLPSpanExporter` no load,
      embora o cliente local (`RustBindingsAPI`) não use gRPC. O stub evita
      carregar `cygrpc`.
    """
    global _PREPARED
    if _PREPARED:
        return
    _PREPARED = True
    _prepare_mmh3()
    _prepare_chroma_otel_without_cygrpc()


def _prepare_mmh3() -> None:
    global _MMH3_IS_STUB
    try:
        import mmh3  # noqa: F401

        return
    except ImportError:
        sys.modules.pop("mmh3", None)

    stub = types.ModuleType("mmh3")

    def hash(key: str | bytes, seed: int = 0, signed: bool = True) -> int:  # noqa: A001
        frame: types.FrameType | None = sys._getframe(1)
        depth = 0
        while frame is not None and depth < 24:
            name = str(frame.f_globals.get("__name__", ""))
            if name == "chromadb" or name.startswith("chromadb."):
                raise ConfigError(_CHROMA_MMH3_HINT)
            frame = frame.f_back
            depth += 1
        data = key.encode("utf-8") if isinstance(key, str) else key
        value = zlib.crc32(data, seed) & 0xFFFFFFFF
        if signed and value >= 0x80000000:
            value -= 0x100000000
        return value

    stub.hash = hash  # type: ignore[attr-defined]
    sys.modules["mmh3"] = stub
    _MMH3_IS_STUB = True


def _purge_prefix(prefix: str) -> None:
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            sys.modules.pop(name, None)


def _cygrpc_available() -> bool:
    try:
        __import__("grpc._cython.cygrpc")
        return True
    except ImportError:
        _purge_prefix("grpc")
        return False


def _prepare_chroma_otel_without_cygrpc() -> None:
    """Evita `import chromadb` puxar cygrpc via OpenTelemetry."""
    global _OTEL_GRPC_STUB
    if _cygrpc_available():
        return

    parent_name = "opentelemetry.exporter.otlp.proto"
    grpc_name = f"{parent_name}.grpc"
    exporter_name = f"{grpc_name}.trace_exporter"
    try:
        __import__(parent_name)
    except ImportError as exc:
        raise ConfigError(
            "Não foi possível preparar o import do Chroma (pacote OpenTelemetry "
            f"ausente: {exc}). Rode `pip install -r requirements.txt` "
            "(chromadb 1.5.x) ou recrie o ambiente."
        ) from exc

    grpc_pkg = types.ModuleType(grpc_name)
    grpc_pkg.__path__ = []
    grpc_pkg.__package__ = grpc_name
    sys.modules[grpc_name] = grpc_pkg
    parent = sys.modules[parent_name]
    parent.grpc = grpc_pkg  # type: ignore[attr-defined]

    class OTLPSpanExporter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ConfigError(_OTEL_STUB_FAILED_HINT)

        def export(self, *args: object, **kwargs: object) -> None:
            return None

        def shutdown(self, *args: object, **kwargs: object) -> None:
            return None

    exporter = types.ModuleType(exporter_name)
    exporter.OTLPSpanExporter = OTLPSpanExporter  # type: ignore[attr-defined]
    sys.modules[exporter_name] = exporter
    grpc_pkg.trace_exporter = exporter  # type: ignore[attr-defined]
    _OTEL_GRPC_STUB = True
