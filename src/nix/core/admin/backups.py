"""Backups de notas gravados pelo VaultWriter: listar, comparar e restaurar."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nix.config.schema import NixConfig
from nix.core.errors import PathEscapeError, VaultError
from nix.core.models import WriteResult
from nix.core.runtime import Runtime
from nix.core.vault.paths import to_posix

_STAMP = re.compile(r"^\d{8}T\d{6}$")
_MAX_DIFF_LINES = 2000
_MAX_DIFF_BYTES = 512 * 1024


@dataclass(frozen=True)
class BackupEntry:
    stamp: str
    rel_path: str
    created_at: str
    size_bytes: int
    current_exists: bool


@dataclass(frozen=True)
class DiffLine:
    kind: str  # "add", "del", "ctx" ou "hunk"
    text: str


@dataclass(frozen=True)
class BackupDiff:
    entry: BackupEntry
    lines: list[DiffLine]
    added: int
    removed: int
    identical: bool
    truncated: bool
    too_large: bool = False


def list_backups(config: NixConfig, limit: int = 200) -> list[BackupEntry]:
    root = config.safety.backup_path
    if not root.is_dir():
        return []
    vault = _vault_root(config)
    entries: list[BackupEntry] = []
    stamps = sorted((child for child in root.iterdir() if child.is_dir() and _STAMP.match(child.name)), reverse=True)
    for folder in stamps:
        for file in sorted(folder.rglob("*")):
            if not file.is_file():
                continue
            rel = file.relative_to(folder).as_posix()
            entries.append(
                BackupEntry(
                    stamp=folder.name,
                    rel_path=rel,
                    created_at=_stamp_iso(folder.name),
                    size_bytes=file.stat().st_size,
                    current_exists=vault is not None and (vault / rel).is_file(),
                )
            )
            if len(entries) >= limit:
                return entries
    return entries


def backup_file(config: NixConfig, stamp: str, rel_path: str) -> Path:
    """Resolve o arquivo de backup sem sair de safety.backup_dir."""
    if not _STAMP.match(stamp):
        raise VaultError(f"Backup {stamp!r} inválido. Abra a lista de backups de novo.")
    root = config.safety.backup_path.resolve()
    posix = to_posix(rel_path)
    candidate = (root / stamp / posix).resolve()
    if not candidate.is_relative_to(root / stamp):
        raise PathEscapeError(f"{posix} sai da pasta de backups. Abra a lista de backups de novo.")
    if not candidate.is_file():
        raise VaultError(
            f"O backup {stamp}/{posix} não existe mais. "
            "Pode ter expirado por safety.backup_retention_days; abra a lista de novo."
        )
    return candidate


def diff_backup(config: NixConfig, stamp: str, rel_path: str) -> BackupDiff:
    source = backup_file(config, stamp, rel_path)
    posix = to_posix(rel_path)
    vault = _vault_root(config)
    current_path = vault / posix if vault is not None else None
    exists = current_path is not None and current_path.is_file()
    size = source.stat().st_size
    entry = BackupEntry(
        stamp=stamp,
        rel_path=posix,
        created_at=_stamp_iso(stamp),
        size_bytes=size,
        current_exists=exists,
    )
    current_size = current_path.stat().st_size if exists and current_path is not None else 0
    if max(size, current_size) > _MAX_DIFF_BYTES:
        # difflib é quadrático: arquivo grande trava a requisição. O download continua disponível.
        return BackupDiff(entry, [], 0, 0, identical=False, truncated=False, too_large=True)
    old = _read(source)
    new = _read(current_path) if exists and current_path is not None else ""
    lines: list[DiffLine] = []
    added = removed = 0
    raw = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"backup {stamp}",
        tofile="atual" if exists else "atual (removida)",
        lineterm="",
        n=3,
    )
    for index, line in enumerate(raw):
        if index < 2:
            continue
        if line.startswith("@@"):
            lines.append(DiffLine("hunk", line))
        elif line.startswith("+"):
            added += 1
            lines.append(DiffLine("add", line[1:]))
        elif line.startswith("-"):
            removed += 1
            lines.append(DiffLine("del", line[1:]))
        else:
            lines.append(DiffLine("ctx", line[1:]))
    truncated = len(lines) > _MAX_DIFF_LINES
    return BackupDiff(
        entry=entry,
        lines=lines[:_MAX_DIFF_LINES],
        added=added,
        removed=removed,
        identical=not lines and exists,
        truncated=truncated,
    )


def restore_backup(runtime: Runtime, stamp: str, rel_path: str) -> WriteResult:
    """Grava o backup por cima da nota. O estado atual ganha o próprio backup antes."""
    posix = to_posix(rel_path)
    if not posix.lower().endswith(".md"):
        raise VaultError(f"Só notas .md podem ser restauradas pela UI. Copie {posix} à mão.")
    content = _read(backup_file(runtime.config, stamp, posix))
    writer = runtime.writer
    if writer.resolve(posix).is_file():
        written = writer.update_note(posix, content, mode="replace", confirm=True)
    else:
        written = writer.create_note(posix, content)
    return runtime.writeback.after_write(written)


def _vault_root(config: NixConfig) -> Path | None:
    return config.vault.root if config.vault.path.strip() else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise VaultError(f"Não foi possível ler {path}: {exc}. Verifique as permissões.") from exc


def _stamp_iso(stamp: str) -> str:
    parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return parsed.isoformat().replace("+00:00", "Z")
