"""Handoff: no máximo um aberto por projeto, reivindicado uma única vez."""

from __future__ import annotations

from nix.core.brain.store import BrainStore, HandoffRecord
from nix.core.errors import ConfigError


def create(project_key: str, body: str, session_key: str = "", store: BrainStore | None = None) -> HandoffRecord:
    text = body.strip()
    if not text:
        raise ConfigError("O handoff está vazio. Descreva onde a sessão parou e rode de novo.")
    target = store or BrainStore()
    created = target.create_handoff(project_key, session_key, text)
    found = target.offered_handoff(project_key)
    if found is None or found.id != created:
        raise ConfigError("O handoff foi gravado, mas não está aberto. Rode `brain_handoff_list` para ver o estado.")
    return found


def accept(project_key: str, consumer: str, store: BrainStore | None = None) -> dict[str, object]:
    who = consumer.strip() or "desconhecido"
    won, body, owner = (store or BrainStore()).accept_handoff(project_key, who)
    if won:
        return {"accepted": True, "text": body, "claimed_by": owner}
    if owner:
        return {
            "accepted": False,
            "text": "",
            "claimed_by": owner,
            "message": f"O handoff já foi reivindicado por {owner}.",
        }
    return {
        "accepted": False,
        "text": "",
        "claimed_by": "",
        "message": "Não há handoff aberto neste projeto. Crie um com `brain_handoff_create`.",
    }


def cancel(project_key: str, store: BrainStore | None = None) -> dict[str, object]:
    removed = (store or BrainStore()).cancel_handoff(project_key)
    if not removed:
        raise ConfigError("Não há handoff aberto neste projeto para cancelar.")
    return {"cancelled": True, "project": project_key}


def listed(project_key: str, store: BrainStore | None = None) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "status": row.status,
            "body": row.body,
            "session": row.session_key,
            "claimed_by": row.consumed_by,
        }
        for row in (store or BrainStore()).list_handoffs(project_key)
    ]
