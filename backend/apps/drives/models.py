"""
Recruitment drives: a company's recruiting day at a university or job fair
(the South Sudan pilot). Students scan the drive's QR code to sign up and
see its roles, or a member of the company's team signs them up at the desk
and scans their transcripts, so nobody has to carry paper.

An assisted signup creates the account without a password. The student
gets an email to claim it: they set a password, which also confirms the
email and records their consent to the documents uploaded for them.
Unclaimed accounts are deleted after UNCLAIMED_DAYS
(manage.py purge_unclaimed_signups).
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils.text import slugify

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L
UNCLAIMED_DAYS = 14


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class RecruitmentDrive(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="drives")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    # Short code people can type in if the QR code won't scan.
    code = models.CharField(max_length=8, unique=True)
    location = models.CharField(max_length=200, blank=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    description = models.TextField(blank=True)
    opportunities = models.ManyToManyField("opportunities.Opportunity", blank=True, related_name="drives")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_on"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = new_code()
            while RecruitmentDrive.objects.filter(code=self.code).exists():
                self.code = new_code()
        if not self.slug:
            base = slugify(f"{self.company.name} {self.name}")[:160] or "drive"
            slug, n = base, 2
            while RecruitmentDrive.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def public_url(self) -> str:
        return f"{settings.FRONTEND_URL.rstrip('/')}/d/{self.code}"


class DriveRegistration(models.Model):
    class Method(models.TextChoices):
        SELF = "self", "Signed up from the drive's link"
        ASSISTED = "assisted", "Signed up by the hiring team"

    drive = models.ForeignKey(RecruitmentDrive, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drive_registrations")
    method = models.CharField(max_length=10, choices=Method.choices)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # The assistant confirmed the student agreed, at the desk, to the signup
    # and to their documents being scanned. The student confirms again by
    # claiming the account.
    desk_consent_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["drive", "student"], name="uq_drive_registration")]

    def __str__(self):
        return f"{self.student} at {self.drive}"
