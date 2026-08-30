"""Textos de apresentação dos modelos de embedding (só CLI)."""

from __future__ import annotations

from typing import NamedTuple

from nix.config.embedding_models import EMBEDDING_MODELS, EmbeddingModelSpec, spec_for


class EmbeddingPresentation(NamedTuple):
    languages: str
    cpu: str
    use_when: str


_PRESENTATION: dict[str, EmbeddingPresentation] = {
    "BAAI/bge-m3": EmbeddingPresentation(
        languages="PT e EN (melhor)",
        cpu="lento",
        use_when="Padrão. Máxima qualidade; máquina com folga.",
    ),
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": EmbeddingPresentation(
        languages="PT e EN (bom)",
        cpu="leve",
        use_when="Recomendado em máquina fraca com notas em português.",
    ),
    "sentence-transformers/all-MiniLM-L6-v2": EmbeddingPresentation(
        languages="inglês",
        cpu="mais leve",
        use_when="Vault só em inglês; o sync mais rápido.",
    ),
    "BAAI/bge-small-en-v1.5": EmbeddingPresentation(
        languages="inglês",
        cpu="mais leve",
        use_when="Inglês; alternativa pequena ao MiniLM-L6.",
    ),
}

_FALLBACK = EmbeddingPresentation(languages="—", cpu="—", use_when="—")

_missing_copy = [spec.name for spec in EMBEDDING_MODELS if spec.name not in _PRESENTATION]
if _missing_copy:
    raise RuntimeError("Falta texto de apresentação na CLI para: " + ", ".join(_missing_copy))


def presentation_for(name: str) -> EmbeddingPresentation:
    return _PRESENTATION.get(name, _FALLBACK)


def labeled_model_rows() -> list[tuple[EmbeddingModelSpec, EmbeddingPresentation]]:
    return [(spec, presentation_for(spec.name)) for spec in EMBEDDING_MODELS]


def sync_model_hint(model_name: str) -> str:
    spec = spec_for(model_name)
    copy = presentation_for(model_name)
    if spec is None:
        return (
            "Sem GPU o embedding roda na CPU. Cada nota pode levar minutos. "
            "A barra só avança quando o arquivo termina — não está travado."
        )
    lighter = next(
        (item for item in EMBEDDING_MODELS if item.name != spec.name and item.size_in_gb < spec.size_in_gb),
        None,
    )
    extra = ""
    if lighter is not None and spec.size_in_gb >= 1.0:
        extra = (
            f" Em máquina fraca, troque no nix.toml para {lighter.name!r} "
            f"({lighter.size_label}) e rode `nix sync --full`."
        )
    return (
        f"Modelo {spec.short_name} ({spec.name}), {spec.size_label}, CPU {copy.cpu}. "
        "Sem GPU o embedding roda na CPU; cada nota pode levar minutos. "
        "A barra só avança quando o arquivo termina — não está travado."
        f"{extra}"
    )
