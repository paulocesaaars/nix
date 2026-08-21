"""Varredura e leitura segura do vault."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from nix.config.schema import NixConfig
from nix.core.errors import NoteNotFoundError, VaultError
from nix.core.models import FileMeta, ParsedNote
from nix.core.vault.markdown import parse_markdown
from nix.core.vault.paths import assert_accessible, is_included, rel_to_vault, resolve_in_vault, to_posix


class VaultReader:
    def __init__(self, config: NixConfig) -> None:
        self._config = config
        self._root = config.require_vault()

    @property
    def root(self) -> Path:
        return self._root

    def iter_files(self, *, extra_globs: list[str] | None = None) -> Iterator[FileMeta]:
        include = list(self._config.vault.include)
        if extra_globs:
            include.extend(extra_globs)
        exclude = self._config.vault.exclude
        follow = self._config.vault.follow_symlinks
        seen: set[str] = set()
        for pattern in include:
            for path in self._root.glob(pattern):
                if not path.is_file():
                    continue
                if path.is_symlink() and not follow:
                    target = path.resolve()
                    try:
                        target.relative_to(self._root.resolve())
                    except ValueError:
                        continue
                try:
                    rel = rel_to_vault(self._root, path)
                except VaultError:
                    continue
                if rel in seen or not is_included(rel, include, exclude):
                    continue
                seen.add(rel)
                stat = path.stat()
                yield FileMeta(
                    rel_path=rel,
                    mtime=stat.st_mtime,
                    size_bytes=stat.st_size,
                    is_symlink=path.is_symlink(),
                )

    def iter_markdown(self) -> Iterator[FileMeta]:
        for meta in self.iter_files():
            if meta.rel_path.lower().endswith(".md"):
                yield meta

    def resolve(self, rel_path: str) -> Path:
        return resolve_in_vault(
            self._root,
            rel_path,
            follow_symlinks=self._config.vault.follow_symlinks,
        )

    def exists(self, rel_path: str, *, apply_include: bool = True) -> bool:
        try:
            self._assert_accessible(rel_path, apply_include=apply_include)
            return self.resolve(rel_path).is_file()
        except VaultError:
            return False

    def _assert_accessible(self, rel_path: str, *, apply_include: bool = True) -> str:
        return assert_accessible(
            rel_path,
            self._config.vault.include,
            self._config.vault.exclude,
            apply_include=apply_include,
        )

    def read_text(self, rel_path: str) -> str:
        self._assert_accessible(rel_path)
        path = self.resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(
                f"A nota {rel_path} não existe no vault. "
                "Confira o caminho com as ferramentas MCP `search_notes` ou `read_note`."
            )
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise VaultError(
                f"Encoding inválido em {rel_path}: {exc}. "
                "Salve o arquivo em UTF-8 e rode `nix sync` de novo."
            ) from exc
        except OSError as exc:
            raise VaultError(
                f"Não foi possível ler {rel_path}: {exc}. Verifique permissões no vault."
            ) from exc

    def read_bytes(self, rel_path: str, *, apply_include: bool = True) -> bytes:
        self._assert_accessible(rel_path, apply_include=apply_include)
        path = self.resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(
                f"O arquivo {rel_path} não existe no vault. Confira o caminho relativo."
            )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise VaultError(
                f"Não foi possível ler {rel_path}: {exc}. Verifique permissões no vault."
            ) from exc

    def parse(self, rel_path: str) -> ParsedNote:
        return parse_markdown(to_posix(rel_path), self.read_text(rel_path))

    def max_mtime_and_count(self) -> tuple[float, int]:
        count = 0
        max_mtime = 0.0
        for meta in self.iter_markdown():
            count += 1
            if meta.mtime > max_mtime:
                max_mtime = meta.mtime
        return max_mtime, count
