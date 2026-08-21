"""Extração de texto de anexos PDF referenciados pelas notas."""

from __future__ import annotations

from pathlib import Path

from nix.core.errors import AttachmentError
from nix.core.models import ParsedNote
from nix.core.vault.markdown import extract_attachment_refs, infer_title


def extract_pdf_text(data: bytes) -> str:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError as exc:
        raise AttachmentError(
            "Pacote pypdf não está instalado. Rode `pip install -r requirements.txt`."
        ) from exc
    try:
        reader = PdfReader(BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages).strip()
    except Exception as exc:  # noqa: BLE001
        raise AttachmentError(
            f"Falha ao extrair texto do PDF: {exc}. "
            "Verifique se o arquivo não está corrompido ou protegido por senha."
        ) from exc


def parse_pdf(rel_path: str, data: bytes) -> ParsedNote:
    text = extract_pdf_text(data)
    if not text:
        text = f"(PDF sem texto extraível: {rel_path})"
    title = infer_title(rel_path, {}, text)
    return ParsedNote(
        rel_path=rel_path,
        raw=text,
        body=text,
        frontmatter={"source": "pdf"},
        title=title,
        tags=[],
        links=[],
        headings=[],
    )


def referenced_pdfs(note_body: str, note_rel: str) -> list[str]:
    refs: list[str] = []
    base = note_rel.rsplit("/", 1)[0] if "/" in note_rel else ""
    for ref in extract_attachment_refs(note_body):
        cleaned = ref.replace("\\", "/").lstrip("./")
        if not cleaned.lower().endswith(".pdf"):
            continue
        if "/" not in cleaned and base:
            cleaned = f"{base}/{cleaned}"
        refs.append(cleaned)
    return refs


def is_pdf_path(rel_path: str) -> bool:
    return Path(rel_path).suffix.lower() == ".pdf"
