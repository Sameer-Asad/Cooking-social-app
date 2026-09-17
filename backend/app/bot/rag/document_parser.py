"""
Text extraction for the doc-RAG upload endpoint (Sec 4.5). Dispatches by
declared content-type (browsers are fairly reliable about these for
pdf/docx), with a filename-extension fallback since some upload paths
send a generic application/octet-stream.

Honest limitation: legacy .doc (pre-2007 binary Word format, MIME type
application/msword) has no reliable pure-Python extraction library —
python-docx only reads the modern .docx XML format. .doc uploads are
rejected with a clear message rather than silently returning garbage
bytes decoded as if they were text.
"""

from __future__ import annotations

import io

from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document as DocxDocument

PLAIN_TEXT_TYPES = {"text/plain", "text/markdown"}
PDF_TYPES = {"application/pdf"}
DOCX_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
LEGACY_DOC_TYPES = {"application/msword"}

ACCEPTED_CONTENT_TYPES = PLAIN_TEXT_TYPES | PDF_TYPES | DOCX_TYPES | LEGACY_DOC_TYPES


def _extract_pdf(raw_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx(raw_bytes: bytes) -> str:
    doc = DocxDocument(io.BytesIO(raw_bytes))
    paragraphs = [p.text for p in doc.paragraphs]
    return "\n".join(paragraphs).strip()


def extract_text(content_type: str, raw_bytes: bytes) -> str:
    """Returns extracted plain text, or raises HTTPException(400) for an
    unsupported or unparseable file."""
    if content_type in PLAIN_TEXT_TYPES:
        try:
            return raw_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File isn't valid UTF-8 text.")

    if content_type in PDF_TYPES:
        try:
            text = _extract_pdf(raw_bytes)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Couldn't read this PDF: {exc}"
            )
        if not text:
            raise HTTPException(
                status_code=400,
                detail="No extractable text found in this PDF — it may be a scanned image without OCR.",
            )
        return text

    if content_type in DOCX_TYPES:
        try:
            text = _extract_docx(raw_bytes)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Couldn't read this document: {exc}"
            )
        if not text:
            raise HTTPException(
                status_code=400, detail="No extractable text found in this document."
            )
        return text

    if content_type in LEGACY_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Legacy .doc files aren't supported — please save as .docx, .pdf, or .txt and re-upload.",
        )

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type {content_type!r} — supported: .txt, .md, .pdf, .docx.",
    )
