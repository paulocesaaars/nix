"""Memória de longo prazo persistida como notas no vault."""

from __future__ import annotations

from datetime import UTC, datetime

from nix.core.runtime import Runtime
from nix.core.vault.paths import to_posix


def persist_memory(
    runtime: Runtime, content: str, *, title: str | None = None
) -> dict[str, object]:
    folder = runtime.config.vault.longterm_folder.strip("/")
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    rel = to_posix(f"{folder}/{day}.md")
    heading = title.strip() if title else "Memória"
    block = f"## {heading}\n\n{content.rstrip()}\n"
    if runtime.reader.exists(rel):
        written = runtime.writer.append_to_note(rel, block)
    else:
        body = (
            f"# Memória {day}\n\nNotas duradouras gravadas pelo Nix.\n\n{block}"
        )
        written = runtime.writer.create_note(
            rel, body, {"tags": ["nix", "memoria"], "created": "auto"}
        )
    result = runtime.writeback.after_write(written)
    return {
        "rel_path": result.rel_path,
        "action": result.action,
        "indexed": result.indexed,
        "message": result.message,
    }
