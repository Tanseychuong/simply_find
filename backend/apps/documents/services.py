"""Adding vault documents, attaching copies to applications, and logging access."""

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.analytics.services import client_ip

from .models import Credential, Document, DocumentAccess
from .uploads import clean_upload_or_400


def add_document(owner, upload, *, kind: str, title: str = "", uploaded_by=None, consent: bool = True) -> Document:
    """Put a file in `owner`'s vault through the upload gate.
    `uploaded_by` is set when someone else (a registration assistant) adds it."""
    if kind not in Document.Kind.values:
        raise ValidationError({"kind": "Pick what kind of document this is."})
    if Document.objects.filter(owner=owner).count() >= Document.MAX_PER_USER:
        raise ValidationError({"file": f"You can keep up to {Document.MAX_PER_USER} documents. Delete one first."})
    clean = clean_upload_or_400(upload, "file")
    document = Document(
        owner=owner, kind=kind,
        title=(title or "").strip()[:120] or Document.Kind(kind).label,
        original_filename=clean.original_name, content_type=clean.content_type,
        size=clean.size, sha256=clean.sha256,
        uploaded_by=uploaded_by if uploaded_by and uploaded_by != owner else None,
        consent_at=timezone.now() if consent else None,
    )
    document.file.save(clean.file.name, clean.file, save=False)
    document.save()
    return document


def copy_for_application(document: Document) -> tuple[ContentFile, str]:
    """A separate copy for an application, so the vault and the application
    can each be deleted without touching the other."""
    with document.file.open("rb") as fh:
        data = fh.read()
    suffix = "." + document.file.name.rsplit(".", 1)[-1] if "." in document.file.name else ""
    return ContentFile(data, name=f"{document.sha256[:16]}{suffix}"), document.original_filename or document.title


def stream(file_field, filename: str) -> FileResponse:
    response = FileResponse(file_field.open("rb"), as_attachment=True, filename=filename or "attachment")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def log_access(request, *, owner, label: str, document=None, answer=None, company=None) -> None:
    """Record that someone other than the owner opened the owner's file."""
    viewer = request.user
    if viewer.pk == owner.pk:
        return
    DocumentAccess.objects.create(
        owner=owner, viewer=viewer, viewer_name=viewer.name[:120],
        company=company, company_name=company.name[:200] if company else "",
        document=document, answer=answer, label=label[:200],
        ip_address=client_ip(request.META),
    )


@transaction.atomic
def add_credential(owner, data) -> Credential:
    from .credentials import check_credential, provider_for_url

    if Credential.objects.filter(owner=owner).count() >= Credential.MAX_PER_USER:
        raise ValidationError({"url": f"You can add up to {Credential.MAX_PER_USER} certificates."})
    url = data["url"]
    provider = data.get("provider") or provider_for_url(url) or Credential.Provider.OTHER
    if Credential.objects.filter(owner=owner, url=url).exists():
        raise ValidationError({"url": "You've already added this certificate."})
    credential = Credential.objects.create(
        owner=owner, provider=provider, url=url,
        title=data.get("title", ""), issuer=data.get("issuer", ""), issued_on=data.get("issued_on"),
    )
    return check_credential(credential)
