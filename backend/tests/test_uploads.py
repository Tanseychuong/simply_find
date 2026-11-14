"""The single upload gate: real file type, PDF scripts, image re-encoding, virus scan."""

import io
import socket
import struct
import threading

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.documents.uploads import (
    DOCUMENT_TYPES,
    IMAGE_TYPES,
    UploadRejected,
    clean_upload,
    scan_for_viruses,
)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF"


def _jpeg_with_gps(size=(64, 48)):
    image = Image.new("RGB", size, "red")
    exif = Image.Exif()
    exif[0x8825] = {2: (5.0, 33.0, 0.0)}   # GPSInfo: latitude
    exif[0x010F] = "PhoneMaker"             # camera make
    buf = io.BytesIO()
    image.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


class TestFileType:
    def test_pdf_accepted_and_renamed(self):
        clean = clean_upload(SimpleUploadedFile("My CV (final).pdf", PDF))
        assert clean.kind == "pdf" and clean.content_type == "application/pdf"
        assert clean.file.name.endswith(".pdf") and "CV" not in clean.file.name
        assert clean.original_name == "My CV (final).pdf"
        assert len(clean.sha256) == 64 and clean.size == len(PDF)

    def test_type_comes_from_the_bytes_not_the_name(self):
        clean = clean_upload(SimpleUploadedFile("transcript.png", PDF))
        assert clean.kind == "pdf" and clean.file.name.endswith(".pdf")

    @pytest.mark.parametrize("name, data", [
        ("cv.docx", b"PK\x03\x04word/document.xml"),
        ("cv.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ("cv.pdf", b"MZ\x90\x00 pretending to be a PDF"),
        ("notes.txt", b"just text"),
        ("page.pdf", b"<html><script>alert(1)</script>"),
    ])
    def test_everything_else_refused(self, name, data):
        with pytest.raises(UploadRejected, match="PDF"):
            clean_upload(SimpleUploadedFile(name, data))

    def test_size_limit(self, settings):
        settings.MAX_UPLOAD_MB = 1
        with pytest.raises(UploadRejected, match="1 MB"):
            clean_upload(SimpleUploadedFile("big.pdf", PDF + b"0" * (1024 * 1024)))

    def test_empty_file(self):
        with pytest.raises(UploadRejected):
            clean_upload(SimpleUploadedFile("empty.pdf", b""))

    def test_logos_may_be_webp_but_documents_may_not(self):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, "WEBP")
        assert clean_upload(SimpleUploadedFile("l.webp", buf.getvalue()), allowed=IMAGE_TYPES).kind == "jpeg"
        with pytest.raises(UploadRejected):
            clean_upload(SimpleUploadedFile("l.webp", buf.getvalue()), allowed=DOCUMENT_TYPES)


class TestPdfContent:
    @pytest.mark.parametrize("marker", [b"/JavaScript", b"/JS (app.alert(1))", b"/Launch", b"/EmbeddedFile",
                                        b"/RichMedia", b"/XFA"])
    def test_active_content_refused(self, marker):
        with pytest.raises(UploadRejected, match="scripts or attached files"):
            clean_upload(SimpleUploadedFile("x.pdf", PDF.replace(b"/Type /Catalog", b"/Type /Catalog " + marker)))

    def test_similar_names_are_not_mistaken_for_scripts(self):
        assert clean_upload(SimpleUploadedFile("x.pdf", PDF.replace(b"/Catalog", b"/Catalog /JSONData 1"))).kind == "pdf"

    def test_password_protected_refused(self):
        with pytest.raises(UploadRejected, match="password"):
            clean_upload(SimpleUploadedFile("x.pdf", PDF + b"\n/Encrypt 5 0 R"))


class TestImages:
    def test_metadata_is_stripped(self):
        clean = clean_upload(SimpleUploadedFile("photo.jpg", _jpeg_with_gps()))
        with Image.open(io.BytesIO(clean.file.read())) as image:
            assert not image.getexif()

    def test_big_photos_are_shrunk_for_slow_connections(self):
        clean = clean_upload(SimpleUploadedFile("scan.jpg", _jpeg_with_gps(size=(4000, 3000))))
        with Image.open(io.BytesIO(clean.file.read())) as image:
            assert max(image.size) == 2400

    def test_broken_image_refused(self):
        with pytest.raises(UploadRejected, match="valid image"):
            clean_upload(SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\n" + b"garbage" * 10))

    def test_decompression_bomb_refused(self, monkeypatch):
        monkeypatch.setattr("apps.documents.uploads.MAX_IMAGE_PIXELS", 100)
        with pytest.raises(UploadRejected, match="too large"):
            clean_upload(SimpleUploadedFile("x.jpg", _jpeg_with_gps(size=(20, 20))))


class _FakeClamd:
    """A clamd that answers INSTREAM with a fixed reply."""

    def __init__(self, reply: bytes):
        self.reply = reply
        self.received = b""
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            data = b""
            while True:
                part = conn.recv(65536)
                if not part:
                    break
                data += part
                if data.endswith(struct.pack("!L", 0)):
                    break
            self.received = data
            conn.sendall(self.reply)
        self.server.close()


class TestVirusScan:
    def test_clean_file_passes_and_is_streamed(self, settings):
        clamd = _FakeClamd(b"stream: OK\0")
        settings.CLAMAV_HOST, settings.CLAMAV_PORT = "127.0.0.1", clamd.port
        clean_upload(SimpleUploadedFile("cv.pdf", PDF))
        assert clamd.received.startswith(b"zINSTREAM\0") and PDF in clamd.received

    def test_infected_file_refused(self, settings):
        clamd = _FakeClamd(b"stream: Eicar-Test-Signature FOUND\0")
        settings.CLAMAV_HOST, settings.CLAMAV_PORT = "127.0.0.1", clamd.port
        with pytest.raises(UploadRejected, match="virus scan") as exc:
            clean_upload(SimpleUploadedFile("cv.pdf", PDF))
        assert not exc.value.unavailable

    def test_scanner_down_refuses_when_required(self, settings):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        settings.CLAMAV_HOST, settings.CLAMAV_PORT, settings.CLAMAV_TIMEOUT = "127.0.0.1", free_port, 1
        settings.VIRUS_SCAN_REQUIRED = True
        with pytest.raises(UploadRejected) as exc:
            scan_for_viruses(PDF)
        assert exc.value.unavailable

    def test_no_scanner_configured_but_required_refuses(self, settings):
        settings.VIRUS_SCAN_REQUIRED = True
        with pytest.raises(UploadRejected):
            scan_for_viruses(PDF)

    def test_no_scanner_and_not_required_passes(self, settings):
        settings.VIRUS_SCAN_REQUIRED = False
        scan_for_viruses(PDF)


def test_scanner_outage_is_a_503_bad_file_a_400(settings):
    """clean_upload_or_400 turns an outage into 503, a bad file into 400."""
    from rest_framework.exceptions import APIException, ValidationError

    from apps.documents.uploads import clean_upload_or_400

    settings.VIRUS_SCAN_REQUIRED = True
    with pytest.raises(APIException) as exc:
        clean_upload_or_400(SimpleUploadedFile("cv.pdf", PDF), "cv")
    assert exc.value.status_code == 503
    settings.VIRUS_SCAN_REQUIRED = False
    with pytest.raises(ValidationError):
        clean_upload_or_400(SimpleUploadedFile("cv.docx", b"PK\x03\x04"), "cv")


def test_deploy_check(settings):
    from apps.documents.checks import uploads_are_scanned
    settings.CLAMAV_HOST, settings.VIRUS_SCAN_REQUIRED = "", True
    assert uploads_are_scanned(None)[0].id == "documents.E001"
    settings.VIRUS_SCAN_REQUIRED = False
    assert uploads_are_scanned(None)[0].id == "documents.W001"
    settings.CLAMAV_HOST = "clamav"
    assert uploads_are_scanned(None) == []
