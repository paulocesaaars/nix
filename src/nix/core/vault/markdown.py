"""Parse de Markdown do Obsidian: frontmatter, cabeçalhos, tags e wikilinks."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import frontmatter

from nix.core.models import Heading, ParsedNote, WikiLink, jsonable

_WIKILINK = re.compile(
    r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]"
)
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_INLINE_TAG = re.compile(r"(?<!\S)#([A-Za-z0-9_/\-]+)")
_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_CODE_FENCE = re.compile(r"^(`{3,}|~{3,})")


def _as_tag_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip().lstrip("#") for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip().lstrip("#") for item in value if str(item).strip()]
    return [str(value).strip().lstrip("#")]


def normalize_tags(value: Any) -> list[str]:
    """Normaliza tags (remove `#`, deduplica e preserva a ordem). Aceita lista ou string."""
    seen: set[str] = set()
    tags: list[str] = []
    for tag in _as_tag_list(value):
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def extract_wikilinks(text: str) -> list[WikiLink]:
    links: list[WikiLink] = []
    seen: set[str] = set()
    for match in _WIKILINK.finditer(text):
        target = match.group(1).strip()
        heading = match.group(2).strip() if match.group(2) else None
        alias = match.group(3).strip() if match.group(3) else None
        key = f"{target}#{heading or ''}"
        if key in seen:
            continue
        seen.add(key)
        links.append(WikiLink(target=target, heading=heading, alias=alias))
    return links


def extract_attachment_refs(text: str) -> list[str]:
    """Caminhos de anexos (pdf e afins) referenciados na nota."""
    refs: list[str] = []
    for match in _WIKILINK.finditer(text):
        target = match.group(1).strip()
        if _looks_like_attachment(target):
            refs.append(target)
    for match in _MD_LINK.finditer(text):
        href = match.group(2).strip()
        if _looks_like_attachment(href) and not href.startswith(("http://", "https://")):
            refs.append(href.split("?", 1)[0])
    return refs


def _looks_like_attachment(path: str) -> bool:
    lowered = path.lower().split("#", 1)[0].split("?", 1)[0]
    return lowered.endswith(".pdf")


def extract_inline_tags(text: str) -> list[str]:
    tags: list[str] = []
    in_code = False
    fence = ""
    for line in text.splitlines():
        fence_match = _CODE_FENCE.match(line.strip())
        if fence_match:
            marker = fence_match.group(1)[0] * len(fence_match.group(1))
            if not in_code:
                in_code = True
                fence = marker
            elif line.strip().startswith(fence[0] * len(fence)):
                in_code = False
                fence = ""
            continue
        if in_code:
            continue
        for match in _INLINE_TAG.finditer(line):
            tags.append(match.group(1))
    return tags


def extract_headings(body: str) -> list[Heading]:
    lines = body.splitlines()
    raw: list[tuple[int, str, int]] = []
    in_code = False
    fence_char = ""
    fence_len = 0
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        fence_match = _CODE_FENCE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_code:
                in_code = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif stripped.startswith(fence_char * fence_len):
                in_code = False
            continue
        if in_code:
            continue
        heading_match = _HEADING.match(line)
        if heading_match:
            raw.append((len(heading_match.group(1)), heading_match.group(2).strip(), idx))

    headings: list[Heading] = []
    stack: list[tuple[int, str]] = []
    for i, (level, title, start) in enumerate(raw):
        end = (raw[i + 1][2] - 1) if i + 1 < len(raw) else len(lines)
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = " > ".join(item[1] for item in stack)
        headings.append(
            Heading(level=level, title=title, start_line=start, end_line=end, path=path)
        )
    return headings


def infer_title(rel_path: str, frontmatter: dict[str, Any], body: str) -> str:
    for key in ("title", "titulo"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    stem = rel_path.rsplit("/", 1)[-1]
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return stem


def parse_markdown(rel_path: str, raw: str) -> ParsedNote:
    post = frontmatter.loads(raw)
    fm = jsonable(dict(post.metadata or {}))
    if not isinstance(fm, dict):
        fm = {}
    body = post.content or ""
    tags = _as_tag_list(fm.get("tags"))
    for tag in extract_inline_tags(body):
        if tag not in tags:
            tags.append(tag)
    return ParsedNote(
        rel_path=rel_path,
        raw=raw,
        body=body,
        frontmatter=fm,
        title=infer_title(rel_path, fm, body),
        tags=tags,
        links=extract_wikilinks(body),
        headings=extract_headings(body),
    )


@dataclass(frozen=True)
class FrontmatterSplit:
    """YAML cru, corpo e o deslocamento para converter linhas do corpo em linhas do arquivo.

    `body` é o mesmo texto que `frontmatter.loads` entrega (é o que `extract_headings` e o
    chunker numeram, a partir de 1). `body_line_offset` soma-se a essa linha para obter a
    linha do arquivo bruto, frontmatter incluído: linha_arquivo = linha_corpo + offset.
    """

    yaml_text: str
    body: str
    body_line_offset: int
    has_frontmatter: bool
    prefix: str
    suffix: str


def _line_core(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith(("\n", "\r")):
        return line[:-1]
    return line


def _is_fence_line(line: str) -> bool:
    """Cerca de fechamento: `---` no início da linha, como o python-frontmatter."""
    return re.fullmatch(r"-{3,}\s*", _line_core(line)) is not None


def _is_opening_fence_line(line: str) -> bool:
    """Cerca de abertura depois do branco inicial que `str.strip` descarta."""
    return re.fullmatch(r"-{3,}\s*", _line_core(line).strip()) is not None


def _opening_fence_index(lines: list[str]) -> int | None:
    index = 0
    total = len(lines)
    while index < total and _line_core(lines[index]).strip() == "":
        index += 1
    if index < total and _is_opening_fence_line(lines[index]):
        return index
    return None


def _like_frontmatter(raw: str) -> str:
    """Mesma normalização de quebras de `frontmatter.loads` (`\\r\\n` → `\\n`)."""
    return raw.replace("\r\n", "\n")


def _closing_fence_end(raw: str) -> int | None:
    """Índice logo após a cerca de fechamento, na cópia com `\\n`."""
    lines = _like_frontmatter(raw).splitlines(keepends=True)
    opening = _opening_fence_index(lines)
    if opening is None:
        return None
    total = 0
    for index, line in enumerate(lines):
        total += len(line)
        if index > opening and _is_fence_line(line):
            return total
    return None


def _offset_after_closing_fence(normalized: str, fence_end: int) -> int:
    """Linha da cerca de fechamento mais as linhas em branco que o strip remove."""
    closed_by_newline = fence_end > 0 and normalized[fence_end - 1 : fence_end] == "\n"
    closing_line = normalized.count("\n", 0, fence_end)
    if not closed_by_newline:
        closing_line += 1
    after = normalized[fence_end:]
    lead = after[: len(after) - len(after.lstrip())]
    return closing_line + lead.count("\n")


def _body_line_offset(raw: str, body: str, *, has_frontmatter: bool, fence_end: int) -> int:
    """Deslocamento do corpo para a linha do arquivo bruto.

    O corpo de `frontmatter.loads` já está com `\\r\\n` trocado por `\\n` e sem o
    branco que o strip remove. A busca usa uma cópia com a mesma normalização.
    Se o corpo não aparecer e houver frontmatter, o deslocamento sai da cerca
    de fechamento — não devolve 0 em silêncio.
    """
    normalized = _like_frontmatter(raw)
    if body:
        start = fence_end if has_frontmatter else 0
        idx = normalized.find(body, start)
        if idx >= 0:
            return normalized.count("\n", 0, idx)
    if not has_frontmatter:
        return 0
    return _offset_after_closing_fence(normalized, fence_end)


def split_frontmatter(raw: str) -> FrontmatterSplit:
    """Separa o bloco YAML do corpo sem reformatar o arquivo.

    O branco antes da primeira cerca é ignorado na detecção, como em
    `frontmatter.loads`, e preservado em `prefix` junto com a cerca de abertura.
    """
    lines = raw.splitlines(keepends=True)
    opening = _opening_fence_index(lines)
    prefix = ""
    yaml_text = ""
    suffix = raw
    has_frontmatter = False
    if opening is not None:
        for index in range(opening + 1, len(lines)):
            if not _is_fence_line(lines[index]):
                continue
            has_frontmatter = True
            prefix = "".join(lines[: opening + 1])
            yaml_text = "".join(lines[opening + 1 : index])
            suffix = "".join(lines[index:])
            break
    body = frontmatter.loads(raw).content or ""
    fence_end = _closing_fence_end(raw) if has_frontmatter else 0
    offset = _body_line_offset(
        raw,
        body,
        has_frontmatter=has_frontmatter,
        fence_end=fence_end or 0,
    )
    return FrontmatterSplit(
        yaml_text=yaml_text,
        body=body,
        body_line_offset=offset,
        has_frontmatter=has_frontmatter,
        prefix=prefix,
        suffix=suffix,
    )


def headings_in_file(raw: str) -> tuple[list[Heading], int]:
    """Headings com linhas do arquivo bruto. O inteiro é o deslocamento do corpo."""
    split = split_frontmatter(raw)
    shifted = [
        Heading(
            level=heading.level,
            title=heading.title,
            path=heading.path,
            start_line=heading.start_line + split.body_line_offset,
            end_line=heading.end_line + split.body_line_offset,
        )
        for heading in extract_headings(split.body)
    ]
    return shifted, split.body_line_offset


def _newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _retarget_newlines(text: str, newline: str) -> str:
    """Troca as quebras de `text` pela quebra já usada no arquivo."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\n":
        return unified
    return unified.replace("\n", newline)


def _split_closing_fence(suffix: str) -> tuple[str, str]:
    for sep in ("\r\n", "\n", "\r"):
        if sep in suffix:
            index = suffix.index(sep)
            return suffix[: index + len(sep)], suffix[index + len(sep) :]
    return suffix, ""


def _drop_leading_separator(text: str) -> str:
    if text.startswith("\r\n"):
        return text[2:]
    if text.startswith("\n"):
        return text[1:]
    return text


def replace_frontmatter_yaml(split: FrontmatterSplit, yaml_text: str) -> str:
    """Remonta a nota com o YAML informado e o restante do arquivo intacto."""
    newline = _newline_of(split.prefix + split.yaml_text + split.suffix)
    if not split.has_frontmatter:
        if not yaml_text.strip():
            return split.suffix
        block = yaml_text if yaml_text.endswith(("\n", "\r\n")) else yaml_text + newline
        return f"---{newline}{block}---{newline}{split.suffix}"
    if not yaml_text.strip():
        _closing, after = _split_closing_fence(split.suffix)
        return _drop_leading_separator(after)
    block = yaml_text if yaml_text.endswith(("\n", "\r\n")) else yaml_text + newline
    return split.prefix + block + split.suffix


def prepend_markdown(raw: str, addition: str) -> str:
    """Insere `addition` depois do YAML original e antes do corpo, com uma linha em branco.

    A quebra do acréscimo e da linha em branco é a de `_newline_of` no texto original.
    O YAML já gravado permanece intacto.
    """
    split = split_frontmatter(raw)
    newline = _newline_of(raw)
    text = _retarget_newlines(addition, newline)
    if not text.endswith(newline):
        text += newline
    if not split.has_frontmatter:
        old = raw if raw.endswith(("\n", "\r")) or raw == "" else raw + newline
        return text + newline + old
    closing, after = _split_closing_fence(split.suffix)
    return split.prefix + split.yaml_text + closing + text + newline + _drop_leading_separator(after)


def stable_link_titles(rel_path: str, raw: str) -> frozenset[str]:
    """Títulos que continuam válidos depois de mover o arquivo e não devem ser reescritos.

    Título vindo do frontmatter (ou de um H1, quando não há título no frontmatter) não muda
    com o caminho. Título inferido só do nome do arquivo muda, e o link correspondente é reescrito.
    """
    parsed = parse_markdown(rel_path, raw)
    frontmatter_title = ""
    for key in ("title", "titulo"):
        value = parsed.frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            frontmatter_title = value.strip()
            break
    if frontmatter_title:
        return frozenset({frontmatter_title.lower()})
    stem = rel_path.rsplit("/", 1)[-1]
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    if parsed.title.strip() and parsed.title.strip().lower() != stem.lower():
        return frozenset({parsed.title.strip().lower()})
    return frozenset()


def _norm_rel(path: str) -> str:
    raw = path.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.lstrip("/")


def _leaf(path: str) -> str:
    return _norm_rel(path).rsplit("/", 1)[-1]


def _stem_of(path: str) -> str:
    name = _leaf(path)
    if name.lower().endswith(".md"):
        return name[:-3]
    return name


def _resolve_relative(source_rel: str, href: str) -> str | None:
    raw = unquote(href.strip()).replace("\\", "/")
    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "obsidian://", "/")):
        return None
    source = _norm_rel(source_rel)
    directory = source.rsplit("/", 1)[0] if "/" in source else ""
    parts = [part for part in directory.split("/") if part] if directory else []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _relative_between(source_rel: str, dest_rel: str) -> str:
    source = _norm_rel(source_rel)
    directory = source.rsplit("/", 1)[0] if "/" in source else ""
    src_parts = [part for part in directory.split("/") if part] if directory else []
    dest_parts = [part for part in _norm_rel(dest_rel).split("/") if part]
    shared = 0
    while shared < len(src_parts) and shared < len(dest_parts) and src_parts[shared] == dest_parts[shared]:
        shared += 1
    relative = ([".."] * (len(src_parts) - shared)) + dest_parts[shared:]
    if not relative:
        return dest_parts[-1] if dest_parts else ""
    return "/".join(relative)


def _expand_wikilink(target: str, source_rel: str) -> list[str]:
    raw = target.strip().replace("\\", "/")
    found = [raw]
    if raw.startswith("./"):
        found.append(raw[2:])
    if raw.startswith("../") or raw.startswith("./"):
        resolved = _resolve_relative(source_rel, raw)
        if resolved:
            found.append(resolved)
    return found


def matches_moved_target(
    target: str,
    old: str,
    *,
    source_rel: str,
    preserve_titles: frozenset[str],
    allow_stem: bool,
) -> bool:
    old_norm = _norm_rel(old)
    old_lower = old_norm.lower()
    old_no_ext = old_lower[:-3] if old_lower.endswith(".md") else old_lower
    old_leaf = _leaf(old).lower()
    old_stem = _stem_of(old).lower()
    for candidate in _expand_wikilink(target, source_rel):
        normalized = _norm_rel(candidate)
        lower = normalized.lower()
        bare = "/" not in normalized
        if bare and lower in preserve_titles:
            continue
        if lower in {old_lower, old_no_ext}:
            return True
        if bare and allow_stem and lower in {old_leaf, old_stem}:
            return True
    return False


def _replacement_target(old_target: str, new: str, *, short: bool) -> str:
    new_norm = _norm_rel(new)
    is_md = new_norm.lower().endswith(".md")
    had_md = old_target.strip().lower().endswith(".md")
    leaf = _leaf(new_norm)
    stem = leaf[:-3] if leaf.lower().endswith(".md") else leaf
    if short:
        chosen = stem if is_md else leaf
        if is_md and had_md:
            return chosen + ".md"
        return chosen
    if is_md and not had_md:
        return new_norm[:-3]
    return new_norm


def _same_note_path(resolved: str, old: str) -> bool:
    """True se os caminhos são a mesma nota, com ou sem a extensão `.md`."""
    left = _norm_rel(resolved).lower()
    right = _norm_rel(old).lower()
    if left == right:
        return True

    def without_md(path: str) -> str:
        return path[:-3] if path.endswith(".md") else path

    if not left.endswith(".md") and not right.endswith(".md"):
        return False
    return without_md(left) == without_md(right)


def _split_href(href: str) -> tuple[str, str, str, bool]:
    """Devolve caminho, sufixo (`#` ou `?`), título opcional e se a URL usava `<>`."""
    raw = href.strip()
    title = ""
    wrapped = False
    if raw.startswith("<") and ">" in raw:
        end = raw.index(">")
        url = raw[1:end]
        title = raw[end + 1 :]
        wrapped = True
    else:
        pieces = raw.split(None, 1)
        url = pieces[0]
        title = f" {pieces[1]}" if len(pieces) > 1 else ""
    suffix = ""
    for sep in ("#", "?"):
        if sep in url:
            index = url.find(sep)
            suffix = url[index:]
            url = url[:index]
            break
    return url, suffix, title, wrapped


def _format_markdown_target(url: str, suffix: str, title: str, *, wrapped: bool) -> str:
    """Remonta o destino. `<>` voltam se o original usava ou se o caminho tem espaço."""
    core = f"{url}{suffix}"
    if wrapped or any(char.isspace() for char in core):
        core = f"<{core}>"
    if not title:
        return core
    if title[:1].isspace():
        return f"{core}{title}"
    return f"{core} {title}"


def _rewrite_outside_inline_code(text: str, rewrite: Callable[[str], str]) -> str:
    """Aplica `rewrite` fora de crases inline na mesma linha. Cerca fica por conta do chamador."""
    parts: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "`":
            nxt = text.find("`", index)
            if nxt < 0:
                parts.append(rewrite(text[index:]))
                break
            parts.append(rewrite(text[index:nxt]))
            index = nxt
            continue
        end = index + 1
        while end < length and text[end] == "`":
            end += 1
        opener = text[index:end]
        close = text.find(opener, end)
        if close < 0:
            parts.append(rewrite(text[index:]))
            break
        parts.append(text[index : close + len(opener)])
        index = close + len(opener)
    return "".join(parts)


def _iter_code_aware(text: str) -> list[tuple[bool, str]]:
    """Segmenta o texto em (dentro_de_bloco_de_código, linha_com_quebra)."""
    lines = text.splitlines(keepends=True)
    in_code = False
    fence_char = ""
    fence_len = 0
    segments: list[tuple[bool, str]] = []
    for line in lines:
        stripped = line.strip()
        fence_match = _CODE_FENCE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_code:
                in_code = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif stripped.startswith(fence_char * fence_len):
                in_code = False
                fence_char = ""
                fence_len = 0
            segments.append((True, line))
            continue
        segments.append((in_code, line))
    if not lines and text:
        segments.append((False, text))
    return segments


def rewrite_links(
    text: str,
    old: str,
    new: str,
    *,
    source_rel: str = "",
    preserve_titles: frozenset[str] = frozenset(),
    allow_stem: bool = True,
    short: bool = True,
    relative_from: str | None = None,
) -> str:
    """Reescreve wikilinks e links Markdown que apontam de `old` para `new`.

    Cobre `[[alvo]]`, `[[alvo|alias]]`, `[[alvo#heading]]`, `![[alvo]]` e links
    Markdown relativos. Preserva alias e heading. Pula cercas e crases inline.
    A forma curta (stem ou nome do arquivo) só é usada quando `short` é verdadeiro.
    `relative_from`, quando informado, é a pasta de onde o link Markdown reescrito
    é calculado; o casamento continua relativo a `source_rel`.
    """
    link_base = source_rel if relative_from is None else relative_from

    def _wiki(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        if not matches_moved_target(
            target,
            old,
            source_rel=source_rel,
            preserve_titles=preserve_titles,
            allow_stem=allow_stem,
        ):
            return match.group(0)
        replacement = _replacement_target(target, new, short=short)
        heading = match.group(2).strip() if match.group(2) else ""
        alias = match.group(3).strip() if match.group(3) else ""
        rebuilt = replacement
        if heading:
            rebuilt = f"{rebuilt}#{heading}"
        if alias:
            rebuilt = f"{rebuilt}|{alias}"
        return f"[[{rebuilt}]]"

    def _markdown(match: re.Match[str]) -> str:
        url, suffix, title, wrapped = _split_href(match.group(2))
        if url.lower().startswith(("http://", "https://", "mailto:", "obsidian://")):
            return match.group(0)
        resolved = _resolve_relative(source_rel, url)
        if resolved is None or not _same_note_path(resolved, old):
            return match.group(0)
        href = _format_markdown_target(
            _relative_between(link_base, new),
            suffix,
            title,
            wrapped=wrapped,
        )
        return f"[{match.group(1)}]({href})"

    def _plain(chunk: str) -> str:
        return _MD_LINK.sub(_markdown, _WIKILINK.sub(_wiki, chunk))

    parts: list[str] = []
    for in_code, line in _iter_code_aware(text):
        if in_code:
            parts.append(line)
            continue
        ending = ""
        core = line
        if line.endswith("\r\n"):
            core, ending = line[:-2], "\r\n"
        elif line.endswith("\n"):
            core, ending = line[:-1], "\n"
        elif line.endswith("\r"):
            core, ending = line[:-1], "\r"
        parts.append(_rewrite_outside_inline_code(core, _plain) + ending)
    return "".join(parts)
