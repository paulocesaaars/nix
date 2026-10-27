"""Escrita atômica, backup e confinamento ao vault."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from nix.config.schema import NixConfig, VaultSettings
from nix.core.errors import ConfirmationRequiredError, NoteNotFoundError, PathEscapeError, VaultError
from nix.core.index.graph import stem_owner
from nix.core.models import WriteResult, utc_now_iso
from nix.core.vault.frontmatter_edit import remove_keys, set_keys
from nix.core.vault.markdown import (
    extract_inline_tags,
    matches_moved_target,
    normalize_tags,
    parse_markdown,
    prepend_markdown,
    replace_frontmatter_yaml,
    rewrite_links,
    split_frontmatter,
    stable_link_titles,
)
from nix.core.vault.paths import assert_accessible, resolve_in_vault, to_posix
from nix.core.vault.reader import VaultReader

LinkRow = tuple[str, str, list[str], list[str]]
MoveKind = Literal["note", "file"]


def _leaf(rel: str) -> str:
    return to_posix(rel).rsplit("/", 1)[-1]


def _stem_of(rel: str) -> str:
    name = _leaf(rel)
    if name.lower().endswith(".md"):
        return name[:-3]
    return name


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _as_note_rel(rel: str) -> str:
    posix = to_posix(rel.strip())
    leaf = _leaf(posix)
    if "." not in leaf:
        return f"{posix}.md"
    if not leaf.lower().endswith(".md"):
        raise VaultError(f"{posix} não é uma nota Markdown. move_note só move arquivos .md.")
    return posix


def _as_file_rel(rel: str) -> str:
    posix = to_posix(rel.strip())
    if posix.lower().endswith(".md"):
        raise VaultError(f"{posix} é uma nota Markdown. Use move_note para mover notas.")
    return posix


def _normalize_move(src: str, dest: str, kind: MoveKind) -> tuple[str, str]:
    if kind == "note":
        return _as_note_rel(src), _as_note_rel(dest)
    return _as_file_rel(src), _as_file_rel(dest)


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
    def __init__(
        self, config: NixConfig, vault: VaultSettings, reader: VaultReader | None = None
    ) -> None:
        self._config = config
        self._vault = vault
        self._root = config.require_vault(vault.name)
        self._reader = reader or VaultReader(config, vault)

    def resolve(self, rel_path: str) -> Path:
        return resolve_in_vault(
            self._root,
            rel_path,
            follow_symlinks=self._vault.follow_symlinks,
        )

    def _assert_accessible(self, rel_path: str, *, apply_include: bool = True) -> str:
        return assert_accessible(
            rel_path,
            self._vault.include,
            self._vault.exclude,
            apply_include=apply_include,
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
        dest = self._config.vault_backup_dir(self._vault) / stamp / to_posix(rel_path)
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
        root = self._config.vault_backup_dir(self._vault)
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
        meta: dict[str, object] = dict(self._vault.default_frontmatter)
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
        if mode not in ("replace", "patch", "prepend"):
            raise VaultError(f"Modo {mode!r} inválido em {posix}. Use replace, patch ou prepend.")
        if mode == "patch":
            return self.append_to_note(posix, content)
        if mode == "prepend":
            return self._prepend(posix, dest, content)
        if mode == "replace" and self._config.safety.confirm_destructive and not confirm:
            raise ConfirmationRequiredError(
                f"Substituir {posix} é destrutivo. Passe confirm=true na ferramenta MCP."
            )
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

    def _prepend(self, posix: str, dest: Path, content: str) -> WriteResult:
        current = self._reader.read_text(posix, keep_newlines=True)
        updated = prepend_markdown(current, content)
        backup = self._backup(dest, posix)
        try:
            self._atomic_write(dest, updated)
        except OSError as exc:
            raise VaultError(
                f"Falha ao inserir texto em {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="updated",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Texto inserido no início de {posix}.",
        )

    def update_frontmatter(
        self,
        rel_path: str,
        values: dict[str, Any] | None,
        remove: list[str] | None,
    ) -> WriteResult:
        posix = self._assert_accessible(rel_path)
        if not posix.lower().endswith(".md"):
            raise VaultError(
                f"{posix} não é uma nota Markdown. update_frontmatter só edita arquivos .md."
            )
        dest = self.resolve(posix)
        if not dest.is_file():
            raise NoteNotFoundError(
                f"A nota {posix} não existe. Use create_note para criá-la antes de editar o frontmatter."
            )
        if not values and not remove:
            raise VaultError(
                "Nenhuma chave em set ou remove. Informe set para gravar ou remove para apagar chaves do frontmatter."
            )
        raw = self._reader.read_text(posix, keep_newlines=True)
        split = split_frontmatter(raw)
        yaml_text = split.yaml_text
        # set prevalece quando a mesma chave está em set e remove
        if remove:
            kept = [key for key in remove if not values or key not in values]
            yaml_text = remove_keys(yaml_text, kept)
        if values:
            yaml_text = set_keys(yaml_text, values)
        if yaml_text == split.yaml_text and split.has_frontmatter:
            return WriteResult(
                rel_path=posix,
                action="updated",
                chunks_indexed=0,
                indexed=False,
                message=f"Frontmatter de {posix} já estava assim. Nada foi gravado.",
                written=False,
            )
        updated = replace_frontmatter_yaml(split, yaml_text)
        backup = self._backup(dest, posix)
        try:
            self._atomic_write(dest, updated)
        except OSError as exc:
            raise VaultError(
                f"Falha ao gravar o frontmatter de {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        return WriteResult(
            rel_path=posix,
            action="updated",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Frontmatter de {posix} atualizado.",
        )

    def manage_tags(self, rel_path: str, add: list[str], remove: list[str]) -> WriteResult:
        posix = self._assert_accessible(rel_path)
        if not posix.lower().endswith(".md"):
            raise VaultError(f"{posix} não é uma nota Markdown. manage_tags só altera tags de arquivos .md.")
        dest = self.resolve(posix)
        if not dest.is_file():
            raise NoteNotFoundError(
                f"A nota {posix} não existe. Use create_note para criá-la antes de alterar as tags."
            )
        if not add and not remove:
            raise VaultError(
                "Nenhuma tag em add ou remove. Informe add e/ou remove para alterar as tags do frontmatter."
            )
        raw = self._reader.read_text(posix, keep_newlines=True)
        split = split_frontmatter(raw)
        parsed = parse_markdown(posix, raw)
        parsed_tags = normalize_tags(parsed.frontmatter.get("tags"))
        removed = set(normalize_tags(remove))
        added = normalize_tags(add)
        merged: list[str] = [tag for tag in parsed_tags if tag not in removed]
        seen = set(merged)
        for tag in added:
            if tag in seen:
                continue
            seen.add(tag)
            merged.append(tag)
        inline = _unique(extract_inline_tags(split.body))
        inline_note = ""
        if inline:
            inline_note = " Tags inline do corpo não foram alteradas: " + ", ".join(inline) + "."
        if merged == parsed_tags:
            listed = ", ".join(merged) if merged else "(nenhuma)"
            return WriteResult(
                rel_path=posix,
                action="updated",
                chunks_indexed=0,
                indexed=False,
                message=f"Tags de {posix} já estavam assim: {listed}.{inline_note}",
                written=False,
            )
        yaml_text = set_keys(split.yaml_text, {"tags": merged})
        updated = replace_frontmatter_yaml(split, yaml_text)
        backup = self._backup(dest, posix)
        try:
            self._atomic_write(dest, updated)
        except OSError as exc:
            raise VaultError(
                f"Falha ao gravar as tags de {posix}: {exc}. Verifique permissões no vault."
            ) from exc
        listed = ", ".join(merged) if merged else "(nenhuma)"
        return WriteResult(
            rel_path=posix,
            action="updated",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=f"Tags de {posix} atualizadas: {listed}.{inline_note}",
        )

    def move_path(
        self,
        src: str,
        dest: str,
        *,
        kind: MoveKind,
        update_links: bool = True,
        overwrite: bool = False,
        confirm: bool = False,
        indexed_links: list[LinkRow] | None = None,
    ) -> WriteResult:
        src_posix, dest_posix = _normalize_move(src, dest, kind)
        apply_include = kind == "note"
        src_posix = self._assert_accessible(src_posix, apply_include=apply_include)
        dest_posix = self._assert_accessible(dest_posix, apply_include=apply_include)
        if src_posix.lower() == dest_posix.lower():
            raise VaultError(
                f"Origem e destino são o mesmo caminho ({src_posix}). Informe um destino diferente."
            )
        src_path = self.resolve(src_posix)
        if not src_path.is_file():
            raise NoteNotFoundError(
                f"O arquivo {src_posix} não existe no vault. Confira o caminho com list_notes ou read_note."
            )
        dest_path = self.resolve(dest_posix)
        backup: str | None = None
        if dest_path.exists():
            if not overwrite:
                raise VaultError(
                    f"O destino {dest_posix} já existe. Passe overwrite=true e confirm=true para substituí-lo."
                )
            if not confirm:
                raise ConfirmationRequiredError(
                    f"Sobrescrever {dest_posix} é destrutivo. Passe overwrite=true e confirm=true na ferramenta MCP."
                )
            backup = self._backup(dest_path, dest_posix)
        preserve = frozenset[str]()
        if kind == "note":
            preserve = stable_link_titles(src_posix, self._reader.read_text(src_posix))
        rows = list(indexed_links or [])
        owner = stem_owner(((rel, title) for rel, title, _links, _tags in rows), src_posix)
        if owner is not None and owner.lower() == src_posix.lower():
            allow_stem = True
        elif owner is None:
            allow_stem = not self._filename_taken(_leaf(src_posix), src_posix)
        else:
            allow_stem = False
        short = not self._filename_taken(_leaf(dest_posix), src_posix)
        planned, pending = self._plan_link_rewrites(
            src_posix,
            dest_posix,
            preserve=preserve,
            allow_stem=allow_stem,
            short=short,
            update_links=update_links,
            indexed_links=rows,
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(src_path, dest_path)
        except OSError as exc:
            raise VaultError(
                f"Falha ao mover {src_posix} para {dest_posix}: {exc}. Verifique permissões no vault."
            ) from exc
        updated: list[str] = []
        try:
            for rel, rewritten in planned:
                path = self.resolve(rel)
                link_backup = self._backup(path, rel)
                if backup is None:
                    backup = link_backup
                self._atomic_write(path, rewritten)
                updated.append(rel)
        except OSError as exc:
            done = ", ".join(updated) if updated else "nenhuma"
            raise VaultError(
                f"O arquivo foi movido para {dest_posix}, mas a atualização dos links falhou ({exc}). "
                f"Notas já reescritas: {done}. Ajuste os wikilinks restantes e rode `nix sync` "
                "ou a ferramenta MCP `sync_index`."
            ) from exc
        message = f"Arquivo movido de {src_posix} para {dest_posix}."
        if updated:
            message += f" Links atualizados em {len(updated)} nota(s)."
        if pending:
            message += (
                f" {len(pending)} nota(s) fora de include/exclude não foram alteradas: "
                + ", ".join(pending)
                + ". Ajuste vault.include ou vault.exclude se quiser atualizá-las."
            )
        return WriteResult(
            rel_path=dest_posix,
            action="moved",
            chunks_indexed=0,
            indexed=False,
            backup_path=backup,
            message=message,
            moved_from=src_posix,
            links_updated=updated,
            links_pending=pending,
        )

    def _filename_taken(self, name: str, ignore_rel: str) -> bool:
        name_l = name.lower()
        ignore = to_posix(ignore_rel).lower()
        root = self._root
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [item for item in dirnames if not item.startswith(".")]
            for filename in filenames:
                if filename.lower() != name_l:
                    continue
                rel = Path(dirpath, filename).relative_to(root).as_posix()
                if rel.lower() == ignore:
                    continue
                return True
        return False

    def _plan_link_rewrites(
        self,
        src: str,
        dest: str,
        *,
        preserve: frozenset[str],
        allow_stem: bool,
        short: bool,
        update_links: bool,
        indexed_links: list[LinkRow],
    ) -> tuple[list[tuple[str, str]], list[str]]:
        if not update_links:
            return [], []
        origin_text: str | None
        try:
            origin_text = self._reader.read_text(src, keep_newlines=True)
        except VaultError:
            origin_text = None
        pending: list[str] = []
        seen_pending: set[str] = set()
        forced: set[str] = set()
        for rel, _title, links, _tags in indexed_links:
            rel_n = to_posix(rel)
            if rel_n in (src, dest):
                continue
            mentions = any(
                matches_moved_target(
                    target,
                    src,
                    source_rel=rel_n,
                    preserve_titles=preserve,
                    allow_stem=allow_stem,
                )
                for target in links
            )
            if not mentions:
                continue
            try:
                self._assert_accessible(rel_n)
            except PathEscapeError:
                if rel_n not in seen_pending:
                    pending.append(rel_n)
                    seen_pending.add(rel_n)
                continue
            forced.add(rel_n)
        needles = {item.lower() for item in (_leaf(src), _stem_of(src)) if item}
        planned: list[tuple[str, str]] = []
        seen: set[str] = set()

        def consider(rel_n: str, text: str) -> None:
            if rel_n in seen:
                return
            seen.add(rel_n)
            rewritten = rewrite_links(
                text,
                src,
                dest,
                source_rel=rel_n,
                preserve_titles=preserve,
                allow_stem=allow_stem,
                short=short,
            )
            if rewritten != text:
                planned.append((rel_n, rewritten))

        for meta in self._reader.iter_markdown():
            rel_n = to_posix(meta.rel_path)
            if rel_n in (src, dest):
                continue
            try:
                text = self._reader.read_text(rel_n, keep_newlines=True)
            except VaultError:
                continue
            haystack = unquote(text).lower()
            if rel_n not in forced and not any(needle in haystack for needle in needles):
                continue
            consider(rel_n, text)
        for rel_n in sorted(forced - seen):
            if rel_n in (src, dest):
                continue
            try:
                consider(rel_n, self._reader.read_text(rel_n, keep_newlines=True))
            except VaultError:
                continue
        if origin_text is not None:
            rewritten = rewrite_links(
                origin_text,
                src,
                dest,
                source_rel=src,
                preserve_titles=preserve,
                allow_stem=allow_stem,
                short=short,
                relative_from=dest,
            )
            if rewritten != origin_text:
                planned.append((dest, rewritten))
        return planned, pending
