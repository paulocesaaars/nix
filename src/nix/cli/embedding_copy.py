"""Tabela de apresentação dos modelos no `nix init`."""

from __future__ import annotations

from nix.config.embedding_models import EMBEDDING_MODELS, EmbeddingModelSpec
from nix.config.embedding_present import EmbeddingPresentation, presentation_for


def labeled_model_rows() -> list[tuple[EmbeddingModelSpec, EmbeddingPresentation]]:
    return [(spec, presentation_for(spec.name)) for spec in EMBEDDING_MODELS]
