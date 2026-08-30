"""Catálogo técnico dos modelos de embedding suportados.

Uma única tabela alimenta a validação da config, o `nix init` e o
registro no FastEmbed. Textos de apresentação (quando usar, CPU) ficam
na CLI (`nix.cli.embedding_copy`).
"""

from __future__ import annotations

from typing import Literal, NamedTuple

PoolingName = Literal["cls", "mean"]


class EmbeddingModelSpec(NamedTuple):
    name: str
    short_name: str
    size_label: str
    size_in_gb: float
    dim: int
    pooling: PoolingName
    model_file: str
    additional_files: tuple[str, ...]
    license: str
    needs_fastembed_register: bool


EMBEDDING_MODELS: tuple[EmbeddingModelSpec, ...] = (
    EmbeddingModelSpec(
        name="BAAI/bge-m3",
        short_name="bge-m3",
        size_label="~2,3 GB",
        size_in_gb=2.27,
        dim=1024,
        pooling="cls",
        model_file="onnx/model.onnx",
        additional_files=("onnx/model.onnx_data",),
        license="mit",
        needs_fastembed_register=True,
    ),
    EmbeddingModelSpec(
        name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        short_name="MiniLM-multi",
        size_label="~220 MB",
        size_in_gb=0.22,
        dim=384,
        pooling="mean",
        model_file="onnx/model.onnx",
        additional_files=(),
        license="apache-2.0",
        needs_fastembed_register=False,
    ),
    EmbeddingModelSpec(
        name="sentence-transformers/all-MiniLM-L6-v2",
        short_name="MiniLM-L6",
        size_label="~90 MB",
        size_in_gb=0.09,
        dim=384,
        pooling="mean",
        model_file="onnx/model.onnx",
        additional_files=(),
        license="apache-2.0",
        needs_fastembed_register=False,
    ),
    EmbeddingModelSpec(
        name="BAAI/bge-small-en-v1.5",
        short_name="bge-small",
        size_label="~67 MB",
        size_in_gb=0.067,
        dim=384,
        pooling="cls",
        model_file="onnx/model.onnx",
        additional_files=(),
        license="mit",
        needs_fastembed_register=False,
    ),
)

SUPPORTED_EMBEDDING_MODELS: tuple[str, ...] = tuple(spec.name for spec in EMBEDDING_MODELS)

_BY_NAME: dict[str, EmbeddingModelSpec] = {spec.name: spec for spec in EMBEDDING_MODELS}


def spec_for(name: str) -> EmbeddingModelSpec | None:
    return _BY_NAME.get(name)


def default_embedding_model() -> str:
    return EMBEDDING_MODELS[0].name
