"""Catálogo técnico dos modelos de embedding suportados.

Uma única tabela alimenta a validação da config, o `nix init` e o
registro no FastEmbed. O texto de quando usar fica em
`nix.config.embedding_present`, usado pela CLI e pela interface.
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
        name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        short_name="lulu",
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
        name="BAAI/bge-m3",
        short_name="spitz",
        size_label="~2,3 GB",
        size_in_gb=2.27,
        dim=1024,
        pooling="cls",
        model_file="onnx/model.onnx",
        additional_files=("onnx/model.onnx_data",),
        license="mit",
        needs_fastembed_register=True,
    ),
)

SUPPORTED_EMBEDDING_MODELS: tuple[str, ...] = tuple(spec.name for spec in EMBEDDING_MODELS)

_BY_NAME: dict[str, EmbeddingModelSpec] = {spec.name: spec for spec in EMBEDDING_MODELS}


def spec_for(name: str) -> EmbeddingModelSpec | None:
    return _BY_NAME.get(name)


def resolve_embedding_model(raw: str) -> str | None:
    """Id do Hugging Face a partir do próprio id ou da raça (`lulu`, `spitz`).

    O número da tabela do `nix init` não entra aqui: a ordem do catálogo não é um id estável.
    """
    text = raw.strip().strip('"').strip("'")
    if text in _BY_NAME:
        return text
    folded = text.casefold()
    for spec in EMBEDDING_MODELS:
        if spec.short_name.casefold() == folded:
            return spec.name
    return None


def embedding_model_choices() -> str:
    return ", ".join(f"{spec.short_name} ({spec.name})" for spec in EMBEDDING_MODELS)


def unsupported_embedding_message(raw: str) -> str:
    shown = raw.strip().strip('"').strip("'")
    return (
        f"index.embedding_model={shown!r} não é suportado. Use um de: {embedding_model_choices()}. "
        "Depois rode `nix sync --full`."
    )


def default_embedding_model() -> str:
    return EMBEDDING_MODELS[0].name
