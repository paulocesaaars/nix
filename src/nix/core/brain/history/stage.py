"""Cópia temporária só de leitura do histórico nativo, com permissão do usuário."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from nix.config.paths import default_state_dir


def stage_readonly(source: Path) -> Path:
    """Copia o histórico para o estado do Nix e tira a escrita e os outros usuários."""
    directory = default_state_dir() / "history"
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"prev-{uuid.uuid4().hex}.jsonl"
    shutil.copyfile(source, dest)
    os.chmod(dest, stat.S_IREAD)
    if sys.platform != "win32":
        os.chmod(dest, stat.S_IRUSR)
        return dest
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        return dest
    subprocess.run(
        ["icacls", str(dest), "/inheritance:r", "/grant:r", f"{user}:(R)"],
        check=False,
        capture_output=True,
        text=True,
    )
    return dest


def discard(path: Path | None) -> None:
    if path is None:
        return
    try:
        if sys.platform == "win32":
            os.chmod(path, stat.S_IWRITE)
        path.unlink(missing_ok=True)
    except OSError:
        return
