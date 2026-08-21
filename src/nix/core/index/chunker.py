"""Chunking consciente da estrutura Markdown."""

from __future__ import annotations

import re

import tiktoken

from nix.config.schema import IndexSettings
from nix.core.models import Chunk, ParsedNote

_CODE_FENCE = re.compile(r"^(`{3,}|~{3,})")
_SENTENCE = re.compile(r"(?<=[.!?。])\s+")


class Chunker:
    def __init__(self, settings: IndexSettings) -> None:
        self._size = settings.chunk_size_tokens
        self._overlap = settings.chunk_overlap_tokens
        self._min = settings.min_chunk_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._enc.encode(text))

    def chunk_note(self, note: ParsedNote, file_id: str, *, mtime: float = 0.0) -> list[Chunk]:
        folder = note.rel_path.rsplit("/", 1)[0] if "/" in note.rel_path else ""
        sections = self._sections(note)
        merged = self._merge_small(sections)
        pieces: list[tuple[str, str, int | None, int | None]] = []
        for heading_path, text, start, end in merged:
            pieces.extend(self._split_section(heading_path, text, start, end))

        chunks: list[Chunk] = []
        for ordinal, piece in enumerate(pieces):
            heading, body, line_start, line_end = piece
            text = body.strip()
            if not text:
                continue
            prefix = note.title if not heading else f"{note.title} > {heading}"
            embed_text = f"{prefix}\n\n{text}"
            chunks.append(
                Chunk(
                    id=f"{file_id}:{ordinal}",
                    file_id=file_id,
                    ordinal=ordinal,
                    heading_path=heading,
                    content=text,
                    embed_text=embed_text,
                    token_count=self.count(text),
                    start_line=line_start,
                    end_line=line_end,
                    title=note.title,
                    rel_path=note.rel_path,
                    tags=list(note.tags),
                    folder=folder,
                    mtime=mtime,
                )
            )
        if not chunks:
            body = note.body.strip() or note.title
            chunks.append(
                Chunk(
                    id=f"{file_id}:0",
                    file_id=file_id,
                    ordinal=0,
                    heading_path="",
                    content=body,
                    embed_text=f"{note.title}\n\n{body}",
                    token_count=self.count(body),
                    start_line=1,
                    end_line=body.count("\n") + 1,
                    title=note.title,
                    rel_path=note.rel_path,
                    tags=list(note.tags),
                    folder=folder,
                    mtime=mtime,
                )
            )
        return chunks

    def _sections(self, note: ParsedNote) -> list[tuple[str, str, int, int]]:
        lines = note.body.splitlines()
        if not note.headings:
            text = note.body.strip()
            return [("", text, 1, max(1, len(lines)))]
        preamble_end = note.headings[0].start_line - 1
        sections: list[tuple[str, str, int, int]] = []
        if preamble_end > 0:
            preamble = "\n".join(lines[:preamble_end]).strip()
            if preamble:
                sections.append(("", preamble, 1, preamble_end))
        for heading in note.headings:
            # linhas do corpo são 1-indexadas relativas ao body
            start = heading.start_line
            end = heading.end_line
            block = "\n".join(lines[start - 1 : end]).strip()
            if block:
                sections.append((heading.path, block, start, end))
        return sections

    def _merge_small(
        self, sections: list[tuple[str, str, int, int]]
    ) -> list[tuple[str, str, int, int]]:
        if not sections:
            return []
        merged: list[tuple[str, str, int, int]] = []
        buf_path, buf_text, buf_start, buf_end = sections[0]
        for path, text, start, end in sections[1:]:
            if self.count(buf_text) < self._min:
                buf_text = f"{buf_text}\n\n{text}"
                buf_end = end
                if not buf_path:
                    buf_path = path
            else:
                merged.append((buf_path, buf_text, buf_start, buf_end))
                buf_path, buf_text, buf_start, buf_end = path, text, start, end
        merged.append((buf_path, buf_text, buf_start, buf_end))
        return merged

    def _split_section(
        self, heading_path: str, text: str, start: int | None, end: int | None
    ) -> list[tuple[str, str, int | None, int | None]]:
        if self.count(text) <= self._size:
            return [(heading_path, text, start, end)]
        blocks = self._split_preserving_code(text)
        out: list[tuple[str, str, int | None, int | None]] = []
        current: list[str] = []
        current_tokens = 0
        overlap_text = ""
        for block in blocks:
            block_tokens = self.count(block)
            if current and current_tokens + block_tokens > self._size:
                joined = "\n\n".join(current).strip()
                out.append((heading_path, joined, start, end))
                overlap_text = self._tail(joined)
                current = [overlap_text, block] if overlap_text else [block]
                current_tokens = self.count("\n\n".join(current))
            else:
                current.append(block)
                current_tokens += block_tokens
        if current:
            out.append((heading_path, "\n\n".join(current).strip(), start, end))
        return out or [(heading_path, text, start, end)]

    def _tail(self, text: str) -> str:
        if self._overlap <= 0:
            return ""
        tokens = self._enc.encode(text)
        if len(tokens) <= self._overlap:
            return text
        return self._enc.decode(tokens[-self._overlap :]).strip()

    def _split_preserving_code(self, text: str) -> list[str]:
        lines = text.splitlines()
        blocks: list[str] = []
        buf: list[str] = []
        in_code = False
        fence_char = ""
        fence_len = 0

        def flush() -> None:
            if buf:
                chunk = "\n".join(buf).strip()
                if chunk:
                    blocks.append(chunk)
                buf.clear()

        for line in lines:
            stripped = line.strip()
            fence = _CODE_FENCE.match(stripped)
            if fence:
                marker = fence.group(1)
                if not in_code:
                    flush()
                    in_code = True
                    fence_char = marker[0]
                    fence_len = len(marker)
                    buf.append(line)
                elif stripped.startswith(fence_char * fence_len):
                    buf.append(line)
                    flush()
                    in_code = False
                else:
                    buf.append(line)
                continue
            if in_code:
                buf.append(line)
                continue
            if not stripped:
                flush()
                continue
            buf.append(line)
            if self.count("\n".join(buf)) > self._size:
                paragraph = "\n".join(buf)
                buf.clear()
                blocks.extend(self._split_sentences(paragraph))
        flush()
        return blocks or [text]

    def _split_sentences(self, text: str) -> list[str]:
        parts = [p.strip() for p in _SENTENCE.split(text) if p.strip()]
        if not parts:
            return [text]
        out: list[str] = []
        buf = ""
        for part in parts:
            candidate = f"{buf} {part}".strip() if buf else part
            if buf and self.count(candidate) > self._size:
                out.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            out.append(buf)
        return out
