"""Escrita atômica, backup e confinamento ao vault."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from nix.config.schema import NixConfig
from nix.core.errors import ConfirmationRequiredError, NoteNotFoundError, VaultError
from nix.core.models import WriteResult, utc_now_iso
from nix.core.vault.paths import assert_accessible, resolve_in_vault, to_posix
from nix.core.vault.reader import VaultReader


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, datetime):
        return json.dumps(value.isoformat(), ensure_ascii=False)
    if isinstance(value, date):
        return json.dumps(value.isoformat(), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _frontmatter_block(data: dict[str, object]) -> str:
    if not data:
        return ""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _heading_level(heading: str) -> int:
    stripped = heading.lstrip()
    n = 0
    for char in stripped:
        if char != "#":
            break
        n += 1
    return n


def _append_in_section(current: str, heading: str, addition: str) -> str:
    """Insere após a seção cujo cabeçalho casa a linha inteira (não substring)."""
    heading_n = heading.strip()
    lines = current.splitlines(keepends=True)
    idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == heading_n:
            idx = i
            break
    if idx is None:
        return current.rstrip() + f"\n\n{heading_n}\n\n" + addition
    level = _heading_level(heading_n)
    insert_at = len(lines)
    for j in range(idx + 1, len(lines)):
        stripped = lines[j].lstrip()
        if not stripped.startswith("#"):
            continue
        hashes = _heading_level(stripped)
        if hashes and hashes <= level and (len(stripped) == hashes or stripped[hashes] in " \t"):
            insert_at = j
            break
    before = "".join(lines[:insert_at]).rstrip() + "\n\n"
    after = "".join(lines[insert_at:])
    extra = addition if addition.endswith("\n") else addition + "\n"
    return before + extra + after


class VaultWriter:
    def __init__(self, config: NixConfig, reader: VaultReader | None = None) -> None:
        self._config = config
        self._root = config.require_vault()
        self._reader = reader or VaultReader(config)

    def resolve(self, rel_path: str) -> Path:
        return resolve_in_vault(
            self._root,
            rel_path,
            follow_symlinks=self._config.vault.follow_symlinks,
        )

    def _assert_accessible(self, rel_path: str) -> str:
        return assert_accessible(
            rel_path,
            self._config.vault.include,
            self._config.vault.exclude,
        )

    def _atomic_write(self, dest: Path, content: str) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".nix-", suffix=".tmp", dir=str(dest.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, dest)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def _backup(self, path: Path, rel_path: str) -> str | None:
        if not self._config.safety.backup_before_overwrite or not path.is_file():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        dest = self._config.safety.backup_path / stamp / to_posix(rel_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, dest)
        except OSError as exc:
            raise VaultError(
                f"Não foi possível criar backup de {rel_path} em {dest}: {exc}. "
                "Verifique safety.backup_dir e o espaço em disco."
            ) from exc
        self._prune_backups()
        return str(dest)

    def _prune_backups(self) -> None:
        root = self._config.safety.backup_path
        if not root.is_dir():
            return
        cutoff = datetime.now(UTC) - timedelta(
            days=self._config.safety.backup_retention_days
        )
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                stamped = datetime.strptime(child.name, "%Y%m%dT%H%M%S").replace(
                    tzinfo=UTC
                )
            except ValueError:
                continue
            if stamped < cutoff:
                shutil.rmtree(child, ignore_errors=True)

    def _compose_new(self, content: str, frontmatter: dict[str, object] | None) -> str:
        meta: dict[str, object] = dict(self._config.vault.default_frontmatter)
        if frontmatter:
            meta.update(frontmatter)
        if meta.get("created") == "auto":
            meta["created"] = utc_now_iso()[:10]
        if content.lstrip().startswith("---"):
            return content if content.endswith("\n") else content + "\n"
        return _frontmatter_block(meta) + (content if content.endswith("\n") else content + "\n")

    def create_note(
        self,
        rel_path: str,
        content: str,
        frontmatter: dict[str, object] | None = None,
        *,
        overwrite: bool = False,
        confirm: bool = False,
    ) -> WriteResult:
        posix = to_posix(rel_path)
        if not posix.lower().endswith(".md"):
            posix += ".md"
        posix = self._assert_accessible(posix)
        dest = self.resolve(posix)
        backup: str | None = None
        if dest.exists():
            if not overwrite:
                raise VaultError(
                    f"A nota {posix} já existe. Use append, update com confirm=true "
                    "ou escolha outro caminho."
                )
            if self._config.safety.confirm_destructive and not confirm:
                raise ConfirmationRequiredError(
                    f"Sobrescrever {posix} é destrutivo. Passe confirm=true na ferramenta MCP."
                )
            backup = self._backup(dest, posix)
        try:
            self._atomic_write(dest, self._compose_new(content, frontmatter))
        except OSError as exc:
            raise VaultError(
                f"Falha ao criar {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="created" if not backup else "updated",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Nota {posix} gravada.",
        )

    def append_to_note(self, rel_path: str, content: str, section: str | None = None) -> WriteResult:
        posix = self._assert_accessible(rel_path)
        dest = self.resolve(posix)
        if not dest.is_file():
            raise NoteNotFoundError(
                f"A nota {posix} não existe. Crie-a com create_note antes de anexar."
            )
        current = self._reader.read_text(posix)
        addition = content if content.endswith("\n") else content + "\n"
        if section:
            heading = f"## {section}" if not section.startswith("#") else section
            updated = _append_in_section(current, heading, addition)
        else:
            sep = "" if current.endswith("\n") else "\n"
            updated = current + sep + "\n" + addition
        backup = self._backup(dest, posix)
        try:
            self._atomic_write(dest, updated)
        except OSError as exc:
            raise VaultError(
                f"Falha ao anexar em {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="appended",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Conteúdo anexado em {posix}.",
        )

    def update_note(
        self,
        rel_path: str,
        content: str,
        mode: str = "replace",
        *,
        confirm: bool = False,
    ) -> WriteResult:
        posix = self._assert_accessible(rel_path)
        dest = self.resolve(posix)
        if not dest.is_file():
            raise NoteNotFoundError(
                f"A nota {posix} não existe. Use create_note para criá-la."
            )
        if mode == "replace" and self._config.safety.confirm_destructive and not confirm:
            raise ConfirmationRequiredError(
                f"Substituir {posix} é destrutivo. Passe confirm=true na ferramenta MCP."
            )
        if mode == "patch":
            return self.append_to_note(posix, content)
        backup = self._backup(dest, posix)
        body = content if content.endswith("\n") else content + "\n"
        try:
            self._atomic_write(dest, body)
        except OSError as exc:
            raise VaultError(
                f"Falha ao atualizar {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="updated",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Nota {posix} atualizada.",
        )

    def delete_note(self, rel_path: str, *, confirm: bool = False) -> WriteResult:
        posix = self._assert_accessible(rel_path)
        dest = self.resolve(posix)
        if not dest.is_file():
            raise NoteNotFoundError(
                f"A nota {posix} não existe. Nada foi removido."
            )
        if self._config.safety.confirm_destructive and not confirm:
            raise ConfirmationRequiredError(
                f"Remover {posix} é destrutivo. Passe confirm=true na ferramenta MCP."
            )
        backup = self._backup(dest, posix)
        try:
            dest.unlink()
        except OSError as exc:
            raise VaultError(
                f"Falha ao remover {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="deleted",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Nota {posix} removida.",
        )
