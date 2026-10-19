"""
Upload validation for evidence and artifact files.

Three checks, all of which must pass:
  1. Extension is on an allowlist.
  2. Size is under the configured limit.
  3. The file's leading bytes match its claimed type, so a renamed
     executable or HTML page cannot pass as a PDF or spreadsheet.
"""
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

MAX_UPLOAD_BYTES = getattr(settings, "ICARIS_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)

_ZIP = (b"PK\x03\x04",)
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)  # legacy .doc/.xls

# extension -> accepted leading byte signatures (None = text, checked separately)
SIGNATURES: dict[str, tuple[bytes, ...] | None] = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "docx": _ZIP,
    "xlsx": _ZIP,
    "pptx": _ZIP,
    "doc": _OLE,
    "xls": _OLE,
    "txt": None,
    "csv": None,
    "md": None,
}

ALLOWED_EXTENSIONS = tuple(sorted(SIGNATURES))


def _extension(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte character may be cut at the end of the sample.
        if exc.start < len(head) - 4:
            return False
    lowered = head.lstrip().lower()
    # Refuse markup that a browser would render as a page.
    return not lowered.startswith((b"<!doctype html", b"<html", b"<script", b"<svg"))


@deconstructible
class EvidenceFileValidator:
    """Model-field validator; reusable across FileFields."""

    def __init__(self, allowed=ALLOWED_EXTENSIONS, max_bytes=MAX_UPLOAD_BYTES):
        self.allowed = tuple(allowed)
        self.max_bytes = max_bytes

    def __call__(self, upload):
        ext = _extension(upload.name)
        if ext not in self.allowed:
            raise ValidationError(
                "File type .%(ext)s is not allowed. Allowed types: %(allowed)s.",
                code="invalid_extension",
                params={"ext": ext or "(none)", "allowed": ", ".join(self.allowed)},
            )
        if upload.size > self.max_bytes:
            raise ValidationError(
                "File is too large (%(size).1f MB). The limit is %(limit).0f MB.",
                code="file_too_large",
                params={"size": upload.size / 1048576, "limit": self.max_bytes / 1048576},
            )
        upload.seek(0)
        head = upload.read(2048)
        upload.seek(0)
        expected = SIGNATURES.get(ext)
        if expected is None:
            ok = _looks_like_text(head)
        else:
            ok = head.startswith(expected)
        if not ok:
            raise ValidationError(
                "The file contents do not match a .%(ext)s file.",
                code="content_mismatch",
                params={"ext": ext},
            )

    def __eq__(self, other):
        return (
            isinstance(other, EvidenceFileValidator)
            and self.allowed == other.allowed
            and self.max_bytes == other.max_bytes
        )


validate_evidence_file = EvidenceFileValidator()


@deconstructible
class RandomizedUploadPath:
    """Store uploads under a random name so paths never reveal or reuse user input."""

    def __init__(self, prefix: str):
        self.prefix = prefix.rstrip("/")

    def __call__(self, instance, filename):
        ext = _extension(filename)
        name = uuid.uuid4().hex + (f".{ext}" if ext else "")
        return f"{self.prefix}/{name}"

    def __eq__(self, other):
        return isinstance(other, RandomizedUploadPath) and self.prefix == other.prefix
