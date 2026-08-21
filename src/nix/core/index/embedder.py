"""Embeddings locais via FastEmbed, com carregamento preguiçoso."""

from __future__ import annotations

from collections.abc import Sequence

from nix.core.errors import ConfigError
from nix.observability.logging import get_logger
from nix.observability.stdio import capture_library_stdout

logger = get_logger("nix.index.embedder")

_CUSTOM_REGISTERED = False


def _register_missing_fastembed_models() -> None:
    """O FastEmbed 0.8 não lista BAAI/bge-m3; o ONNX oficial é registrado na hora."""
    global _CUSTOM_REGISTERED
    if _CUSTOM_REGISTERED:
        return
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    with capture_library_stdout():
        known = {
            str(item.get("model") or item.get("model_name") or "")
            for item in TextEmbedding.list_supported_models()
        }
        if "BAAI/bge-m3" not in known:
            logger.info(
                "Registrando BAAI/bge-m3 no FastEmbed (ONNX oficial, ~2,3 GB no primeiro download)."
            )
            TextEmbedding.add_custom_model(
                model="BAAI/bge-m3",
                pooling=PoolingType.CLS,
                normalization=True,
                sources=ModelSource(hf="BAAI/bge-m3"),
                dim=1024,
                model_file="onnx/model.onnx",
                description="Multilíngue, 1024 dimensões. Registrado pelo Nix.",
                license="mit",
                size_in_gb=2.27,
                additional_files=["onnx/model.onnx_data"],
            )
    _CUSTOM_REGISTERED = True


class Embedder:
    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: object | None = None
        self._dim: int | None = None

    def _ensure(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding

            logger.info("Carregando modelo de embedding %s", self.model_name)
            try:
                with capture_library_stdout():
                    _register_missing_fastembed_models()
                    self._model = TextEmbedding(model_name=self.model_name)
            except ValueError as exc:
                raise ConfigError(
                    f"Não foi possível carregar o embedding {self.model_name!r}: {exc}. "
                    "Confira index.embedding_model na configuração. "
                    "O padrão BAAI/bge-m3 baixa ~2,3 GB na primeira execução "
                    "(precisa de rede até o Hugging Face)."
                ) from exc
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure()
        vectors: list[list[float]] = []
        with capture_library_stdout():
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
