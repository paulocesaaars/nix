"""Parse de Markdown do Obsidian: frontmatter, cabeçalhos, tags e wikilinks."""

from __future__ import annotations

import re
from typing import Any

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
