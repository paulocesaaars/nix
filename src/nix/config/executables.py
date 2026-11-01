"""Nomes dos dois binários publicados: o completo e o do hook.

O Nuitka 4.3, em modo onefile com cache, recalcula o CRC de cada arquivo do
payload em toda partida. O binário completo tem centenas de MB e passa de 1 s,
acima dos 300 ms do hook. O `nix-hook` leva só `core/brain`.

O artefato da release usa o nome com versão (`nix-2.4.0-linux-amd64` e
`nix-hook-2.4.0-linux-amd64`). Instalado, vira `{NIX_HOME}/bin/nix` e
`nix-hook` (com `.exe` no Windows).
"""

from __future__ import annotations

import sys
from pathlib import Path

from nix.config.paths import env_home


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


def cli_to_launch(argv0: str, executable: str) -> Path:
    """Binário completo que grava a página. No hook, o irmão; no completo, ele mesmo."""
    programs = [Path(raw) for raw in (argv0, executable) if raw]
    for program in programs:
        stem, _ext = _split(program)
        if _is_hook_stem(stem):
            sibling = cli_binary_beside(program)
            if sibling.is_file():
                return sibling
        elif program.is_file() and _is_cli_stem(stem):
            return program
    installed = _installed_cli()
    if installed is not None:
        return installed
    for program in programs:
        stem, _ext = _split(program)
        if _is_hook_stem(stem):
            return cli_binary_beside(program)
    return cli_binary_beside(Path(executable or argv0))


def _is_hook_stem(stem: str) -> bool:
    return stem == "nix-hook" or stem.startswith("nix-hook-")


def _is_cli_stem(stem: str) -> bool:
    return stem == "nix" or (stem.startswith("nix-") and not _is_hook_stem(stem))


def _installed_cli() -> Path | None:
    home = env_home()
    if home is None:
        return None
    name = "nix.exe" if sys.platform == "win32" else "nix"
    candidate = home / "bin" / name
    return candidate if candidate.is_file() else None


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
