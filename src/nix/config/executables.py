"""Nomes dos dois binários publicados: o completo e o do hook.

O Nuitka 4.3, em modo onefile com cache, recalcula o CRC de cada arquivo do
payload em toda partida. O binário completo tem centenas de MB e passa de 1 s,
acima dos 300 ms do hook (RF-130). O `nix-hook` leva só `core/sessions`.

O artefato da release usa o nome com versão (`nix-2.4.0-linux-amd64` e
`nix-hook-2.4.0-linux-amd64`). Instalado, vira `{NIX_HOME}/bin/nix` e
`nix-hook` (com `.exe` no Windows).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _split(program: Path) -> tuple[str, str]:
    name = program.name
    if name.lower().endswith(".exe"):
        return name[:-4], name[-4:]
    return name, ""


def hook_binary_beside(program: Path) -> Path:
    """Caminho do `nix-hook` irmão de `program`. Se `program` já for o hook, devolve ele."""
    stem, ext = _split(program)
    if stem == "nix-hook" or stem.startswith("nix-hook-"):
        return program
    if stem == "nix":
        return program.with_name("nix-hook" + ext)
    if stem.startswith("nix-"):
        return program.with_name("nix-hook-" + stem[len("nix-") :] + ext)
    return program.with_name("nix-hook" + ext)


def cli_binary_beside(program: Path) -> Path:
    """Binário completo irmão de um `nix-hook`. Se `program` já for o completo, devolve ele."""
    stem, ext = _split(program)
    if stem == "nix-hook":
        return program.with_name("nix" + ext)
    if stem.startswith("nix-hook-"):
        return program.with_name("nix-" + stem[len("nix-hook-") :] + ext)
    return program


def packaged_hook_executable() -> Path | None:
    """`nix-hook` ao lado do processo, quando este é o binário Nuitka e o irmão existe."""
    from nix.config.paths import is_packaged

    if not is_packaged():
        return None
    current = Path(sys.argv[0]).resolve()
    sibling = hook_binary_beside(current)
    if sibling.is_file():
        return sibling
    return None
