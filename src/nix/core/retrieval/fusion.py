"""Reciprocal Rank Fusion."""

from __future__ import annotations

from nix.core.models import RetrievedChunk


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Combina rankings. `weights` pondera cada lista; o score sai normalizado em 0–1."""
    if not rankings:
        return []
    used_weights = weights if weights is not None else [1.0] * len(rankings)
    if len(used_weights) != len(rankings):
        raise ValueError("weights deve ter o mesmo tamanho de rankings.")
    weight_sum = sum(used_weights) or 1.0
    scores: dict[str, float] = {}
    by_id: dict[str, RetrievedChunk] = {}
    for ranking, weight in zip(rankings, used_weights, strict=True):
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + weight / (k + rank)
            if chunk.chunk_id not in by_id or chunk.score > by_id[chunk.chunk_id].score:
                by_id[chunk.chunk_id] = chunk
    # máximo teórico: todos os rankers colocam o mesmo chunk em 1º
    scale = (k + 1) / weight_sum
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fused: list[RetrievedChunk] = []
    for chunk_id, score in ordered:
        base = by_id[chunk_id]
        fused.append(
            RetrievedChunk(
                chunk_id=base.chunk_id,
                file_id=base.file_id,
                rel_path=base.rel_path,
                title=base.title,
                heading_path=base.heading_path,
                content=base.content,
                score=min(1.0, score * scale),
                ordinal=base.ordinal,
                start_line=base.start_line,
                end_line=base.end_line,
                tags=base.tags,
                folder=base.folder,
                mtime=base.mtime,
            )
        )
    return fused
