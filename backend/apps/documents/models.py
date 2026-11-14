"""
A student's document vault, their online-learning credentials, and the log
of who opened their files.

Documents (transcripts, certificates, CVs...) are uploaded once, through the
upload gate (uploads.py), into private storage. Applying to a job attaches
a *copy* of a vault document to the application, so deleting a vault
document never changes what a company already received, and withdrawing
an application deletes only the copy.

Credentials are links to certificates earned online (Coursera, edX, Credly,
LinkedIn Learning, Open Badges). We say exactly how far each was checked:
  * recognised_link: the link points at the provider's own certificate
    pages. That shows where it lives, not that it belongs to this person.
  * verified: an Open Badge whose issuer's record names this person's
    email and isn't revoked or expired (credentials.py).
"""

from django.conf import settings
from django.db import models

from .storage import private_storage, unguessable_name


def vault_file_path(instance, filename):
    return unguessable_name("vault", filename)


class Document(models.Model):
    class Kind(models.TextChoices):
        TRANSCRIPT = "transcript", "Transcript"
        CERTIFICATE = "certificate", "Certificate or diploma"
        CV = "cv", "CV"
        RECOMMENDATION = "recommendation", "Recommendation letter"
        ID_DOCUMENT = "id_document", "ID document"
        OTHER = "other", "Other"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=120)
    file = models.FileField(upload_to=vault_file_path, storage=private_storage)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=60)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    # Set when someone else uploaded it for the student (assisted signup at a
    # recruitment drive). consent_at records when the student agreed.
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    consent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    MAX_PER_USER = 20

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_kind_display()})"


class Credential(models.Model):
    class Provider(models.TextChoices):
        COURSERA = "coursera", "Coursera"
        EDX = "edx", "edX"
        CREDLY = "credly", "Credly"
        LINKEDIN_LEARNING = "linkedin_learning", "LinkedIn Learning"
        OPEN_BADGE = "open_badge", "Open Badge"
        OTHER = "other", "Other"

    class Check(models.TextChoices):
        UNCHECKED = "unchecked", "Not checked"
        RECOGNISED_LINK = "recognised_link", "Link on the provider's site"
        VERIFIED = "verified", "Verified with the issuer"
        FAILED = "failed", "Couldn't be verified"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credentials")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    title = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=500)
    issued_on = models.DateField(null=True, blank=True)
    check_status = models.CharField(max_length=20, choices=Check.choices, default=Check.UNCHECKED)
    check_detail = models.CharField(max_length=300, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    MAX_PER_USER = 30

    class Meta:
        ordering = ["-issued_on", "-created_at"]

    def __str__(self):
        return self.title


class DocumentAccess(models.Model):
    """Someone other than the owner opened one of the owner's files.
    Students can read their own log; it is kept after the file is gone."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_accesses")
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    viewer_name = models.CharField(max_length=120)
    company = models.ForeignKey("companies.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    company_name = models.CharField(max_length=200, blank=True)
    document = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True, related_name="accesses")
    answer = models.ForeignKey(
        "companies.ApplicationAnswer", on_delete=models.SET_NULL, null=True, blank=True, related_name="accesses",
    )
    label = models.CharField(max_length=200)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accessed_at"]
        indexes = [models.Index(fields=["owner", "-accessed_at"])]

    def __str__(self):
        return f"{self.viewer_name} opened {self.label}"
