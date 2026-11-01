"""Varredura e leitura segura da wiki."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from nix.config.schema import NixConfig, WikiSettings
from nix.core.errors import NoteNotFoundError, WikiError
from nix.core.models import FileMeta, ParsedNote
from nix.core.wiki.markdown import parse_markdown
from nix.core.wiki.paths import assert_accessible, is_included, rel_to_wiki, resolve_in_wiki, to_posix


class WikiReader:
    def __init__(self, config: NixConfig, wiki: WikiSettings) -> None:
        self._config = config
        self._vault = wiki
        self._root = config.require_wiki(wiki.name)

    @property
    def root(self) -> Path:
        return self._root

    def iter_files(self, *, extra_globs: list[str] | None = None) -> Iterator[FileMeta]:
        include = list(self._vault.include)
        if extra_globs:
            include.extend(extra_globs)
        exclude = self._vault.exclude
        follow = self._vault.follow_symlinks
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
                    rel = rel_to_wiki(self._root, path)
                except WikiError:
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
        return resolve_in_wiki(
            self._root,
            rel_path,
            follow_symlinks=self._vault.follow_symlinks,
        )

    def exists(self, rel_path: str, *, apply_include: bool = True) -> bool:
        try:
            self._assert_accessible(rel_path, apply_include=apply_include)
            return self.resolve(rel_path).is_file()
        except WikiError:
            return False

    def _assert_accessible(self, rel_path: str, *, apply_include: bool = True) -> str:
        return assert_accessible(
            rel_path,
            self._vault.include,
            self._vault.exclude,
            apply_include=apply_include,
        )

    def read_text(self, rel_path: str, *, keep_newlines: bool = False) -> str:
        """Lê a nota em UTF-8.

        Com `keep_newlines`, `\\r\\n` e `\\n` do arquivo voltam iguais, para a
        regravação não trocar a quebra. Sem isso, a leitura normaliza para `\\n`.
        """
        self._assert_accessible(rel_path)
        path = self.resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(
                f"A nota {rel_path} não existe na wiki. "
                "Confira o caminho com as ferramentas MCP `search_notes` ou `read_note`."
            )
        try:
            # open(), não Path.read_text(): o argumento newline só existe no Python 3.13,
            # e o binário publicado é compilado com 3.12.
            with path.open(encoding="utf-8", newline="" if keep_newlines else None) as handle:
                return handle.read()
        except UnicodeDecodeError as exc:
            raise WikiError(
                f"Encoding inválido em {rel_path}: {exc}. "
                "Salve o arquivo em UTF-8 e rode `nix sync` de novo."
            ) from exc
        except OSError as exc:
            raise WikiError(
                f"Não foi possível ler {rel_path}: {exc}. Verifique permissões na wiki."
            ) from exc

    def read_bytes(self, rel_path: str, *, apply_include: bool = True) -> bytes:
        self._assert_accessible(rel_path, apply_include=apply_include)
        path = self.resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(
                f"O arquivo {rel_path} não existe na wiki. Confira o caminho relativo."
            )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise WikiError(
                f"Não foi possível ler {rel_path}: {exc}. Verifique permissões na wiki."
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
