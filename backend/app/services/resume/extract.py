"""
Resume text extraction. Pure, in-memory, no DB/network — takes the raw
bytes ResumeService already has at upload time (no need to re-read the
saved file from disk). Best-effort: an unreadable/corrupt/unsupported file
must not fail the upload, so every error path returns None rather than
raising.
"""

import io

from docx import Document
from pypdf import PdfReader


def extract_text(filename: str, contents: bytes) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    try:
        if ext == "pdf":
            return _extract_pdf(contents)
        if ext == "docx":
            return _extract_docx(contents)
        # txt, rtf, and anything else: best-effort plain-text decode.
        # RTF control words will leak into the text, but that's still more
        # useful to Tier 1 than nothing, and RTF resumes are rare.
        return contents.decode("utf-8", errors="ignore").strip() or None
    except Exception:  # noqa: BLE001 - never fail the upload over extraction
        return None


def _extract_pdf(contents: bytes) -> str | None:
    reader = PdfReader(io.BytesIO(contents))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip() or None


def _extract_docx(contents: bytes) -> str | None:
    doc = Document(io.BytesIO(contents))
    text = "\n".join(p.text for p in doc.paragraphs)
    return text.strip() or None
