"""Upload validation: size, extension, declared-vs-real MIME, active content.

Fail-closed order of operations:

1. filename shape (no separators, no control characters, bounded length)
2. streaming size cap while staging bytes
3. real magic-byte detection on the staged file
4. active content (SVG/HTML/XML) rejection
5. extension must match the detected family
6. declared MIME must match the detected MIME
7. detected family must be allowed for the declared resource kind
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.storage.sniff import (
    OOXML_DOCX,
    OOXML_PPTX,
    SniffResult,
    detect_mime,
)

MIME_BY_FAMILY: dict[str, tuple[str, frozenset[str]]] = {
    "docx": (OOXML_DOCX, frozenset({".docx"})),
    "pptx": (OOXML_PPTX, frozenset({".pptx"})),
    "pdf": ("application/pdf", frozenset({".pdf"})),
    "png": ("image/png", frozenset({".png"})),
    "jpeg": ("image/jpeg", frozenset({".jpg", ".jpeg"})),
    "mp4": ("video/mp4", frozenset({".mp4", ".m4v"})),
    "webm": ("video/webm", frozenset({".webm"})),
}

KIND_ALLOWED_FAMILIES: dict[str, frozenset[str]] = {
    "WORD": frozenset({"docx"}),
    "SLIDES": frozenset({"pptx"}),
    "VIDEO": frozenset({"mp4", "webm"}),
    "PDF": frozenset({"pdf"}),
    "IMAGE": frozenset({"png", "jpeg"}),
}

VARIANT_INLINE_OK: frozenset[str] = frozenset({"mp4", "webm", "png", "jpeg", "pdf"})

# Operating systems register their own aliases for Office formats: Chrome on a
# desktop with WPS installed reports ``application/wps-office.docx`` for a real
# .docx, and macOS reports ``application/vnd.ms-powerpoint`` style types. Those
# are not contradictions — the bytes still have to match the family below.
MIME_ALIASES: dict[str, frozenset[str]] = {
    "docx": frozenset({"application/wps-office.docx", "application/vnd.ms-word"}),
    "pptx": frozenset({"application/wps-office.pptx", "application/vnd.ms-powerpoint"}),
    "pdf": frozenset({"application/x-pdf", "application/acrobat"}),
    "mp4": frozenset({"video/x-m4v", "application/mp4"}),
    "webm": frozenset({"video/x-matroska"}),
    "png": frozenset({"image/x-png"}),
    "jpeg": frozenset({"image/pjpeg"}),
}

_FILENAME_RE = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,180}$")


class UploadRejected(Exception):
    """A validation failure that maps to a readable HTTP error."""

    def __init__(self, code: str, message: str, status_code: int = 415) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedUpload:
    family: str
    mime: str
    extension: str
    original_filename: str
    size_bytes: int
    sha256: str
    inline_ok: bool


def normalise_filename(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        raise UploadRejected("RESOURCE_FILENAME_REQUIRED", "缺少文件名", 400)
    if "\\" in name or "/" in name:
        raise UploadRejected("RESOURCE_FILENAME_PATH", "文件名不能包含路径分隔符", 400)
    if name in {".", ".."} or name.startswith("."):
        raise UploadRejected("RESOURCE_FILENAME_PATH", "文件名不能是隐藏文件", 400)
    if not _FILENAME_RE.match(name):
        raise UploadRejected("RESOURCE_FILENAME_INVALID", "文件名包含不允许的字符", 400)
    return name


def _normalise_mime(raw: str | None) -> str:
    return (raw or "").split(";")[0].strip().lower()


def validate_upload(
    *,
    staged: Path,
    filename: str | None,
    declared_mime: str | None,
    kind: str,
    size_bytes: int,
    sha256: str,
    max_bytes: int,
) -> ValidatedUpload:
    """Validate an already-staged upload. Never trusts client metadata."""

    name = normalise_filename(filename)
    if size_bytes > max_bytes:
        raise UploadRejected("RESOURCE_TOO_LARGE", "文件超过大小上限", 413)
    if size_bytes <= 0:
        raise UploadRejected("RESOURCE_EMPTY", "文件为空", 400)

    sniffed: SniffResult = detect_mime(staged)
    if sniffed.is_active_content:
        raise UploadRejected(
            "RESOURCE_ACTIVE_CONTENT_REJECTED",
            "不允许上传 SVG/HTML/XML 等可执行主动内容",
            415,
        )
    allowed = MIME_BY_FAMILY.get(sniffed.family)
    if allowed is None:
        raise UploadRejected(
            "RESOURCE_TYPE_NOT_ALLOWED",
            f"不支持的文件类型（检测为 {sniffed.mime}）",
            415,
        )
    expected_mime, extensions = allowed

    extension = Path(name).suffix.lower()
    if extension not in extensions:
        raise UploadRejected(
            "RESOURCE_EXTENSION_MISMATCH",
            f"扩展名 {extension or '(无)'} 与实际文件类型不符",
            415,
        )

    declared = _normalise_mime(declared_mime)
    accepted_declared = {expected_mime, "application/octet-stream"}
    accepted_declared |= MIME_ALIASES.get(sniffed.family, frozenset())
    if declared and declared not in accepted_declared:
        raise UploadRejected(
            "RESOURCE_MIME_MISMATCH",
            "声明的 Content-Type 与实际文件类型不符",
            415,
        )

    if kind not in KIND_ALLOWED_FAMILIES:
        raise UploadRejected("RESOURCE_KIND_UNKNOWN", "资源类型不受支持", 400)
    if sniffed.family not in KIND_ALLOWED_FAMILIES[kind]:
        raise UploadRejected(
            "RESOURCE_KIND_MISMATCH",
            f"该文件类型不能登记为 {kind} 资源",
            415,
        )

    return ValidatedUpload(
        family=sniffed.family,
        mime=expected_mime,
        extension=extension,
        original_filename=name,
        size_bytes=size_bytes,
        sha256=sha256,
        inline_ok=sniffed.family in VARIANT_INLINE_OK,
    )


__all__ = [
    "KIND_ALLOWED_FAMILIES",
    "MIME_ALIASES",
    "MIME_BY_FAMILY",
    "VARIANT_INLINE_OK",
    "UploadRejected",
    "ValidatedUpload",
    "normalise_filename",
    "validate_upload",
]
