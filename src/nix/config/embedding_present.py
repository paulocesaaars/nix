"""Textos de apresentação dos modelos, usados pela CLI e pela interface."""

from __future__ import annotations

from typing import NamedTuple

from nix.config.embedding_models import EMBEDDING_MODELS, spec_for


class EmbeddingPresentation(NamedTuple):
    use_when: str


_PRESENTATION: dict[str, EmbeddingPresentation] = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": EmbeddingPresentation(
        use_when="Computador com pouca folga. O sync é mais rápido.",
    ),
    "BAAI/bge-m3": EmbeddingPresentation(
        use_when="Computador com CPU, memória e disco de sobra, quando a busca precisa de mais qualidade.",
    ),
}

_FALLBACK = EmbeddingPresentation(use_when="—")

_missing_copy = [spec.name for spec in EMBEDDING_MODELS if spec.name not in _PRESENTATION]
if _missing_copy:
    raise RuntimeError("Falta texto de apresentação para: " + ", ".join(_missing_copy))


def presentation_for(name: str) -> EmbeddingPresentation:
    return _PRESENTATION.get(name, _FALLBACK)


def embedding_choice_label(model_name: str) -> str | None:
    """Rótulo da configuração: raça e quando usar. O valor gravado continua o id."""
    spec = spec_for(model_name)
    if spec is None:
        return None
    return f"{spec.short_name} — {presentation_for(model_name).use_when}"


def sync_model_hint(model_name: str) -> str:
    spec = spec_for(model_name)
    if spec is None:
        return "O embedding roda na CPU. A barra só avança quando o arquivo termina — não está travado."
    pace = "Cada nota pode levar minutos. " if spec.size_in_gb >= 1.0 else ""
    extra = ""
    lighter = next((item for item in EMBEDDING_MODELS if item.size_in_gb < spec.size_in_gb), None)
    if lighter is not None and spec.size_in_gb >= 1.0:
        extra = (
            f" Em computador com pouca folga, troque com `nix config set index.embedding_model {lighter.short_name}` "
            f"({lighter.size_label}) e rode `nix sync --full`."
        )
    return (
        f"Modelo {spec.short_name} ({spec.name}), {spec.size_label}. "
        f"{presentation_for(model_name).use_when} "
        f"O embedding roda na CPU. {pace}"
        "A barra só avança quando o arquivo termina — não está travado."
        f"{extra}"
    )
