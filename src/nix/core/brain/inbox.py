"""Fila de mensagens entre agentes. `pop` entrega uma vez, na mesma transação."""

from __future__ import annotations

from nix.core.brain.store import BrainStore
from nix.core.errors import ConfigError


def send(project_key: str, body: str, recipient: str = "", store: BrainStore | None = None) -> dict[str, object]:
    text = body.strip()
    if not text:
        raise ConfigError("A mensagem está vazia. Escreva o texto e envie de novo.")
    message_id = (store or BrainStore()).send_message(project_key, text, recipient)
    return {"id": message_id, "project": project_key, "recipient": recipient.strip().lower(), "status": "pending"}


def pop(project_key: str, agent: str = "", store: BrainStore | None = None) -> dict[str, object]:
    found = (store or BrainStore()).pop_message(project_key, agent)
    if found is None:
        return {"delivered": False, "text": "", "message": "Não há mensagens esperando."}
    message_id, text = found
    return {"delivered": True, "id": message_id, "text": text}


def listed(project_key: str, store: BrainStore | None = None) -> list[dict[str, object]]:
    return [
        {"id": message_id, "recipient": recipient, "text": text, "status": status}
        for message_id, recipient, text, status in (store or BrainStore()).list_messages(project_key)
    ]


def cancel(message_id: int, store: BrainStore | None = None) -> dict[str, object]:
    if not (store or BrainStore()).cancel_message(message_id):
        raise ConfigError(
            f"A mensagem {message_id} não está pendente. "
            "Ela já foi entregue ou cancelada. Veja a fila com `brain_message_list`."
        )
    return {"cancelled": True, "id": message_id}
