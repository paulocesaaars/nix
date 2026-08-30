"""Embeddings locais via FastEmbed, com carregamento preguiçoso.

Stdout fica capturado por padrão (MCP stdio). A CLI de `sync` interativa
pede `capture_embedder_stdout=False` em `Runtime.from_config`.
"""

from __future__ import annotations

import time
import warnings
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext

from nix.config.embedding_models import EMBEDDING_MODELS, spec_for
from nix.core.errors import ConfigError
from nix.observability.logging import get_logger
from nix.observability.stdio import capture_library_stdout

logger = get_logger("nix.index.embedder")

_CUSTOM_REGISTERED = False


def _register_missing_fastembed_models() -> None:
    """Registra no FastEmbed os modelos do catálogo que a lib não lista."""
    global _CUSTOM_REGISTERED
    if _CUSTOM_REGISTERED:
        return
    from fastembed.common.model_description import ModelSource, PoolingType
    from fastembed.text.text_embedding import TextEmbedding

    pooling_map = {"cls": PoolingType.CLS, "mean": PoolingType.MEAN}
    with capture_library_stdout():
        known = {
            str(item.get("model") or item.get("model_name") or "") for item in TextEmbedding.list_supported_models()
        }
        for spec in EMBEDDING_MODELS:
            if not spec.needs_fastembed_register or spec.name in known:
                continue
            logger.info(
                "Registrando %s no FastEmbed (%s no primeiro download).",
                spec.name,
                spec.size_label,
            )
            TextEmbedding.add_custom_model(
                model=spec.name,
                pooling=pooling_map[spec.pooling],
                normalization=True,
                sources=ModelSource(hf=spec.name),
                dim=spec.dim,
                model_file=spec.model_file,
                description="Registrado pelo Nix a partir do catálogo de embeddings.",
                license=spec.license,
                size_in_gb=spec.size_in_gb,
                additional_files=list(spec.additional_files),
            )
    _CUSTOM_REGISTERED = True


class Embedder:
    def __init__(
        self,
        model_name: str,
        batch_size: int = 32,
        *,
        capture_stdout: bool = True,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.capture_stdout = capture_stdout
        self._model: object | None = None
        self._dim: int | None = None

    def ensure_loaded(self) -> None:
        """Carrega o modelo (e baixa o ONNX na primeira vez)."""
        self._ensure()

    def _load_context(self) -> AbstractContextManager[None]:
        if self.capture_stdout:
            return capture_library_stdout()
        return nullcontext()

    def _ensure(self) -> object:
        if self._model is None:
            logger.info(
                "Carregando modelo de embedding %s. "
                "Na primeira vez o FastEmbed baixa o ONNX; em CPU isso pode levar muitos minutos.",
                self.model_name,
            )
            started = time.perf_counter()
            try:
                from fastembed.text.text_embedding import TextEmbedding

                with self._load_context():
                    _register_missing_fastembed_models()
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            "ignore",
                            message=r"The model .* now uses mean pooling instead of CLS embedding",
                            category=UserWarning,
                        )
                        self._model = TextEmbedding(model_name=self.model_name)
            except ImportError as exc:
                raise ConfigError(
                    f"Não foi possível importar o FastEmbed: {exc}. "
                    "No Windows, o Controle de Aplicativo pode bloquear a DLL "
                    "do mmh3 no Python 3.14. Permita o arquivo .pyd em "
                    ".venv/Lib/site-packages ou recrie o ambiente."
                ) from exc
            except ValueError as exc:
                spec = spec_for(self.model_name)
                size = spec.size_label if spec is not None else "o ONNX"
                raise ConfigError(
                    f"Não foi possível carregar o embedding {self.model_name!r}: {exc}. "
                    "Confira index.embedding_model na configuração. "
                    f"Este modelo baixa {size} na primeira execução "
                    "(precisa de rede até o Hugging Face)."
                ) from exc
            logger.info(
                "Modelo %s pronto em %.1fs.",
                self.model_name,
                time.perf_counter() - started,
            )
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure()
        vectors: list[list[float]] = []
        with self._load_context():
            for vec in model.embed(list(texts), batch_size=self.batch_size):  # type: ignore[attr-defined]
                vectors.append([float(x) for x in vec])
        if vectors and self._dim is None:
            self._dim = len(vectors[0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        result = self.embed([text])
        return result[0] if result else []

    @property
    def dim(self) -> int | None:
        return self._dim
