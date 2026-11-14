"""
One gate for every file a person uploads: CVs, transcripts, certificates,
profile pictures and company logos.

`clean_upload()` decides what a file really is from its first bytes (never
from its name or the browser's Content-Type), refuses anything that isn't
an allowed type, refuses PDFs that carry scripts or attachments, re-encodes
images (which drops their metadata, such as GPS location, and shrinks big
phone photos for slow connections), and scans the result for viruses with
ClamAV when a scanner is configured. It returns a new, safe file with a
name we chose; the uploaded name is kept only as a label.

Limits of the PDF check: it reads the raw bytes, so a script hidden inside
a compressed object stream can slip past it. The virus scan is the second
line of defence, which is why production expects a scanner (checks.py).
"""

import hashlib
import io
import logging
import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

PDF, JPEG, PNG, WEBP = "pdf", "jpeg", "png", "webp"
CONTENT_TYPES = {PDF: "application/pdf", JPEG: "image/jpeg", PNG: "image/png", WEBP: "image/webp"}
EXTENSIONS = {PDF: ".pdf", JPEG: ".jpg", PNG: ".png", WEBP: ".webp"}
DOCUMENT_TYPES = frozenset({PDF, JPEG, PNG})
IMAGE_TYPES = frozenset({JPEG, PNG, WEBP})

# PDF features that run code, open other programs or smuggle files in.
_PDF_DANGEROUS = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/XFA", b"/SubmitForm")
MAX_IMAGE_PIXELS = 40_000_000   # refuse decompression bombs before decoding them


class UploadRejected(Exception):
    """The file can't be accepted. `message` is safe to show the uploader."""

    def __init__(self, message: str, *, unavailable: bool = False):
        super().__init__(message)
        self.message = message
        self.unavailable = unavailable  # True: our problem (scanner down), not the file's


@dataclass
class CleanFile:
    file: ContentFile          # named <sha256 prefix><extension>
    kind: str                  # pdf | jpeg | png | webp
    content_type: str
    size: int
    sha256: str
    original_name: str         # what the uploader called it, clipped; a label only


def sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    return None


def _label(name: str) -> str:
    stem = Path(name or "file").name.replace("\x00", "")
    return stem[-120:] or "file"


def _check_pdf(data: bytes) -> None:
    if b"/Encrypt" in data:
        raise UploadRejected("This PDF is password-protected. Upload a copy without a password.")
    for marker in _PDF_DANGEROUS:
        # "/JS" must not match "/JSON" or similar: check the next byte.
        start = 0
        while (index := data.find(marker, start)) != -1:
            after = data[index + len(marker): index + len(marker) + 1]
            if not after or not (after.isalnum()):
                raise UploadRejected(
                    "This PDF contains scripts or attached files, which we don't accept. "
                    "Save it again with 'Print to PDF' and upload that copy."
                )
            start = index + 1


def _reencode_image(data: bytes, kind: str, max_side: int) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise UploadRejected("That image is too large. Use one under 40 megapixels.")
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except UploadRejected:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
        raise UploadRejected("That file isn't a valid image.")
    image = ImageOps.exif_transpose(image)   # keep the photo upright once EXIF is gone
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side))
    out = io.BytesIO()
    if kind == JPEG or (kind == WEBP and image.mode not in ("RGBA", "LA", "P")):
        image.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
        return out.getvalue(), JPEG
    # PNG and transparent WebP stay lossless PNG (logos with transparency).
    if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        image = image.convert("RGBA")
    image.save(out, "PNG", optimize=True)
    return out.getvalue(), PNG


def scan_for_viruses(data: bytes) -> None:
    """Scan with clamd's INSTREAM command. Raises UploadRejected when the
    file is infected, or (unavailable=True) when a scan is required but the
    scanner can't be reached."""
    host = settings.CLAMAV_HOST
    if not host:
        if settings.VIRUS_SCAN_REQUIRED:
            raise UploadRejected("Uploads are paused for a moment. Please try again later.", unavailable=True)
        return
    try:
        with socket.create_connection((host, settings.CLAMAV_PORT), timeout=settings.CLAMAV_TIMEOUT) as conn:
            conn.sendall(b"zINSTREAM\0")
            for start in range(0, len(data), 64 * 1024):
                chunk = data[start:start + 64 * 1024]
                conn.sendall(struct.pack("!L", len(chunk)) + chunk)
            conn.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = conn.recv(4096)
                if not part:
                    break
                reply += part
    except OSError:
        logger.exception("Virus scanner unreachable at %s:%s", host, settings.CLAMAV_PORT)
        if settings.VIRUS_SCAN_REQUIRED:
            raise UploadRejected("Uploads are paused for a moment. Please try again later.", unavailable=True)
        return
    answer = reply.rstrip(b"\0").decode(errors="replace")
    if answer.endswith("FOUND"):
        logger.warning("Upload rejected by virus scan: %s", answer)
        raise UploadRejected("This file was flagged by our virus scan, so we can't accept it.")
    if not answer.endswith("OK"):
        logger.error("Unexpected virus scanner reply: %s", answer)
        if settings.VIRUS_SCAN_REQUIRED:
            raise UploadRejected("Uploads are paused for a moment. Please try again later.", unavailable=True)


def clean_upload(upload, *, allowed=DOCUMENT_TYPES, max_bytes=None, max_image_side=2400) -> CleanFile:
    """Check, clean and scan one uploaded file. Raises UploadRejected."""
    max_bytes = max_bytes or settings.MAX_UPLOAD_MB * 1024 * 1024
    if upload is None:
        raise UploadRejected("Choose a file to upload.")
    if upload.size is not None and upload.size > max_bytes:
        raise UploadRejected(f"Files must be {max_bytes // (1024 * 1024)} MB or smaller.")
    upload.seek(0)
    data = upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadRejected(f"Files must be {max_bytes // (1024 * 1024)} MB or smaller.")
    if not data:
        raise UploadRejected("That file is empty.")

    kind = sniff(data[:16])
    if kind not in allowed:
        names = ", ".join(sorted(EXTENSIONS[k].lstrip(".").upper() for k in allowed))
        raise UploadRejected(f"Upload a {names} file. Word documents can carry macros, so save them as PDF first.")

    if kind == PDF:
        _check_pdf(data)
    else:
        data, kind = _reencode_image(data, kind, max_image_side)

    scan_for_viruses(data)
    digest = hashlib.sha256(data).hexdigest()
    return CleanFile(
        file=ContentFile(data, name=f"{digest[:32]}{EXTENSIONS[kind]}"),
        kind=kind, content_type=CONTENT_TYPES[kind], size=len(data), sha256=digest,
        original_name=_label(getattr(upload, "name", "")),
    )


def clean_upload_or_400(upload, field: str, **kwargs) -> CleanFile:
    """clean_upload() for DRF views: a rejected file becomes a 400 on
    `field`; a scanner outage becomes a 503."""
    from rest_framework.exceptions import APIException, ValidationError

    try:
        return clean_upload(upload, **kwargs)
    except UploadRejected as exc:
        if exc.unavailable:
            error = APIException(exc.message)
            error.status_code = 503
            raise error
        raise ValidationError({field: exc.message})
