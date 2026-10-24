"""Content-sniffing based file type detection.

We never trust the client-supplied filename extension or Content-Type header alone -
the actual bytes are inspected so a mislabeled or malicious upload is still classified
(or rejected) correctly.
"""

from __future__ import annotations

from app.models.document import SourceType

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_HTML_MARKERS = (b"<!doctype html", b"<html", b"<head", b"<body")


def _looks_like_html(sample: bytes) -> bool:
    lowered = sample.lower().lstrip()
    return any(marker in lowered[:2048] for marker in _HTML_MARKERS)


def _looks_like_docx(content: bytes, filename: str) -> bool:
    return content.startswith(_ZIP_MAGIC) and filename.lower().endswith(".docx")


def sniff_source_type(filename: str, content: bytes) -> SourceType | None:
    """Returns the detected `SourceType`, or None if the content is not one we support."""
    if content.startswith(_PDF_MAGIC):
        return SourceType.PDF
    if _looks_like_docx(content, filename):
        return SourceType.DOCX

    lower_name = filename.lower()
    sample = content[:4096]

    if _looks_like_html(sample) or lower_name.endswith((".html", ".htm")):
        return SourceType.HTML

    if lower_name.endswith((".md", ".markdown")):
        # Markdown has no reliable magic bytes; require it to be valid UTF-8 text.
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return SourceType.MARKDOWN

    return None
