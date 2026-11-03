"""Controle do estado do Mega Brain pela configuração validada."""

from nix.config.editor import set_many
from nix.config.loader import load_config
from nix.core.errors import ConfigError


def configure(wiki: str | None, enabled: bool | None, *, source: str) -> None:
    """Valida a wiki efetiva e grava os campos informados numa transação."""
    config = load_config()
    effective_wiki = config.brain.wiki if wiki is None else wiki.strip()
    if not effective_wiki:
        raise ConfigError("Selecione uma wiki cadastrada para configurar o Mega Brain.")
    chosen = config.get_wiki(effective_wiki)
    updates: list[tuple[str, str, object]] = []
    if wiki is not None:
        updates.append(("brain", "wiki", chosen.name))
    if enabled is not None:
        updates.append(("brain", "enabled", enabled))
    set_many(updates, source=source, persist=True)
