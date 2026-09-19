"""Magic-byte sniffing: the declared MIME type is never trusted.

The detector reads real bytes (and, for OOXML, the real ZIP directory) so a
renamed file cannot pass validation. Active content (SVG/HTML/XML script
containers) is flagged explicitly instead of being treated as an image.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

OOXML_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OOXML_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
OOXML_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HTML_HINT = re.compile(r"<\s*(!doctype\s+html|html|head|body|script|iframe|object|embed)\b", re.I)
_SVG_HINT = re.compile(r"<\s*svg\b", re.I)
_XML_PROLOG = re.compile(r"^\s*<\?xml\b", re.I)


@dataclass(frozen=True)
class SniffResult:
    mime: str
    family: str
    is_active_content: bool


def _sniff_zip(path: Path) -> SniffResult:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return SniffResult("application/octet-stream", "unknown", False)
    if "word/document.xml" in names:
        return SniffResult(OOXML_DOCX, "docx", False)
    if "ppt/presentation.xml" in names:
        return SniffResult(OOXML_PPTX, "pptx", False)
    if "xl/workbook.xml" in names:
        return SniffResult(OOXML_XLSX, "xlsx", False)
    return SniffResult("application/zip", "zip", False)


def _sniff_text(head: bytes) -> SniffResult | None:
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = head.decode("latin-1")
        except UnicodeDecodeError:
            return None
    if not text.strip():
        return None
    if _SVG_HINT.search(text) or (_XML_PROLOG.match(text) and _SVG_HINT.search(text)):
        return SniffResult("image/svg+xml", "svg", True)
    if _HTML_HINT.search(text):
        return SniffResult("text/html", "html", True)
    if _XML_PROLOG.match(text):
        return SniffResult("application/xml", "xml", True)
    return None


def detect_mime(path: Path) -> SniffResult:
    """Detect the real type of an uploaded file from its bytes."""

    with path.open("rb") as stream:
        head = stream.read(4096)
    if not head:
        return SniffResult("application/octet-stream", "empty", False)
    if head[:2] == b"PK" and head[2:4] in {b"\x03\x04", b"\x05\x06", b"\x07\x08"}:
        return _sniff_zip(path)
    if head.startswith(b"%PDF-"):
        return SniffResult("application/pdf", "pdf", False)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return SniffResult("image/png", "png", False)
    if head.startswith(b"\xff\xd8\xff"):
        return SniffResult("image/jpeg", "jpeg", False)
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return SniffResult("image/gif", "gif", False)
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand[:3] in {b"iso", b"mp4", b"avc", b"dash", b"M4V", b"MSN", b"isom"}:
            return SniffResult("video/mp4", "mp4", False)
        if brand in {b"M4A ", b"M4B ", b"M4P "}:
            return SniffResult("audio/mp4", "audio", False)
        return SniffResult("video/mp4", "mp4", False)
    if head.startswith(b"\x1aE\xdf\xa3"):
        return SniffResult("video/webm", "webm", False)
    if head.startswith(b"ID3") or head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return SniffResult("audio/mpeg", "audio", False)
    text = _sniff_text(head[:2048])
    if text is not None:
        return text
    return SniffResult("application/octet-stream", "unknown", False)
