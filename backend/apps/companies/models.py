"""
Company accounts, and in-app applications to the jobs they post.

Lifecycle of a company:
  sign up -> PENDING -> an admin APPROVES it (or REJECTS / SUSPENDS it).
  Only an APPROVED company can post jobs. On top of approval, an admin can
  give it the *verified badge* (is_verified): a verified company's jobs go
  live immediately, everyone else's wait in the normal moderation queue.

A company is its own account, managed by a team: people join it through a
CompanyMembership with a role (owner, admin, recruiter), usually by
accepting a CompanyInvitation sent to their email. A person belongs to at
most one company. The company outlives any one member's account.

A job is an Opportunity with `company` set. Its application_method is
either EXTERNAL (apply on the company's own site, like every other
listing) or IN_APP, in which case the company defines the position's
ApplicationRequirements and applicants answer them in an Application.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.documents.storage import private_files_storage, unguessable_name


# Path segments the API and frontend use under /companies/.
RESERVED_SLUGS = {"me", "review", "join", "new", "admin", "invite", "invitations"}


class CompanyManager(models.Manager):
    def create_with_owner(self, user, **fields):
        """Create a company with `user` as its first owner."""
        company = self.create(created_by=user, **fields)
        CompanyMembership.objects.create(company=company, user=user, role=CompanyMembership.Role.OWNER)
        return company


class Company(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    # Who signed the company up (and accepted the hiring commitments). Kept
    # for the record; what someone can do comes from their membership.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="companies_created",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    website = models.URLField(max_length=500, blank=True)
    logo_url = models.URLField(max_length=1000, blank=True)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=200, blank=True)
    size = models.CharField(max_length=40, blank=True, help_text="e.g. 1-10, 11-50, 51-200, 200+")
    contact_email = models.EmailField(blank=True)
    # When the person signing up confirmed they may act for the company and
    # will use applicant data only to recruit for the role applied to.
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_verified = models.BooleanField(
        default=False, help_text="Verified badge: this company's jobs publish without moderation.",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyManager()

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:200] or "company"
            if base in RESERVED_SLUGS:
                base = f"{base}-company"
            slug, n = base, 2
            while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def can_post(self) -> bool:
        return self.status == self.Status.APPROVED

    @property
    def publishes_directly(self) -> bool:
        return self.can_post and self.is_verified

    def _review(self, reviewer, status, reason=""):
        self.status = status
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def approve(self, reviewer):
        self._review(reviewer, self.Status.APPROVED)

    def reject(self, reviewer, reason):
        self.is_verified = False
        self.verified_at = None
        self._review(reviewer, self.Status.REJECTED, reason)

    def suspend(self, reviewer, reason=""):
        self.is_verified = False
        self.verified_at = None
        self._review(reviewer, self.Status.SUSPENDED, reason)

    def members_with_role(self, *roles):
        qs = self.memberships.select_related("user").filter(user__is_active=True)
        return qs.filter(role__in=roles) if roles else qs

    def notification_emails(self) -> list[str]:
        """Who hears about the account and its applications: active owners
        and admins, plus the hiring contact address."""
        emails = {m.user.email for m in self.members_with_role(CompanyMembership.Role.OWNER, CompanyMembership.Role.ADMIN)}
        if self.contact_email:
            emails.add(self.contact_email)
        return sorted(emails)

    def set_verified(self, reviewer, verified: bool):
        """The badge implies approval, so verifying a pending company approves it too."""
        self.is_verified = verified
        self.verified_at = timezone.now() if verified else None
        if verified and self.status != self.Status.APPROVED:
            self._review(reviewer, self.Status.APPROVED)
        else:
            self.save()


class CompanyMembership(models.Model):
    """A person's place on a company's team."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"          # everything, including the team and roles
        ADMIN = "admin", "Admin"          # company profile, jobs, applicants; invites admins/recruiters
        RECRUITER = "recruiter", "Recruiter"  # jobs and applicants only

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    # One company per person (for now): the dashboard and API act on "my company".
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_membership")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RECRUITER)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["company", "role"])]

    def __str__(self):
        return f"{self.user} ({self.get_role_display()}, {self.company})"

    @classmethod
    def for_user(cls, user):
        """The user's membership (with its company), or None."""
        if user is None or not getattr(user, "pk", None):
            return None
        return cls.objects.select_related("company").filter(user=user).first()

    @property
    def can_manage(self) -> bool:
        """Edit the company profile and invite people (owners and admins)."""
        return self.role in (self.Role.OWNER, self.Role.ADMIN)

    def permissions(self) -> dict:
        """What this member may do, for the frontend to show the right
        controls. The API enforces the same rules (services.py)."""
        is_owner = self.role == self.Role.OWNER
        return {
            "manage_profile": self.can_manage,
            "invite": self.can_manage,
            "invite_owners": is_owner,
            "change_roles": is_owner,
            "remove_admins": is_owner,
            "remove_recruiters": self.can_manage,
        }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CompanyInvitation(models.Model):
    """An emailed, single-use invitation to join a company's team. Only a
    hash of the token is stored; the link in the email is the only copy."""

    VALID_FOR = timedelta(days=7)

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=CompanyMembership.Role.choices,
                            default=CompanyMembership.Role.RECRUITER)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "email"])]

    def __str__(self):
        return f"{self.email} → {self.company} ({self.role})"

    @classmethod
    def issue(cls, company, email, role, invited_by):
        """Create an invitation; returns (invitation, raw_token)."""
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            company=company, email=email, role=role, invited_by=invited_by,
            token_hash=_hash_token(token), expires_at=timezone.now() + cls.VALID_FOR,
        )
        return invitation, token

    @classmethod
    def find(cls, token: str):
        if not token or len(token) > 200:
            return None
        return cls.objects.select_related("company", "invited_by").filter(token_hash=_hash_token(token)).first()

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.expires_at > timezone.now()


class ApplicationRequirement(models.Model):
    """One thing an applicant must provide for an in-app position."""

    class Kind(models.TextChoices):
        SHORT_TEXT = "short_text", "Short answer"
        LONG_TEXT = "long_text", "Long answer"
        FILE = "file", "File upload (CV, transcript, portfolio...)"
        URL = "url", "Link"
        YES_NO = "yes_no", "Yes / No"
        CHOICE = "choice", "Multiple choice"

    opportunity = models.ForeignKey(
        "opportunities.Opportunity", on_delete=models.CASCADE, related_name="requirements",
    )
    label = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SHORT_TEXT)
    help_text = models.CharField(max_length=500, blank=True)
    required = models.BooleanField(default=True)
    options = models.JSONField(default=list, blank=True, help_text="Choices, for multiple-choice requirements.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.label


def application_storage():
    """Private storage for CVs and other application files (apps/documents/storage.py)."""
    return private_files_storage


def application_file_path(instance, filename):
    # Unguessable key; files are only ever handed out through the
    # authenticated download view.
    return unguessable_name("applications", filename)


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEWING = "reviewing", "In review"
        SHORTLISTED = "shortlisted", "Shortlisted"
        REJECTED = "rejected", "Not selected"
        HIRED = "hired", "Hired"
        WITHDRAWN = "withdrawn", "Withdrawn"

    opportunity = models.ForeignKey(
        "opportunities.Opportunity", on_delete=models.CASCADE, related_name="applications",
    )
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    company_note = models.TextField(blank=True, help_text="Private to the company.")
    # When the applicant agreed to share their answers with the company.
    consent_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["opportunity", "applicant"], name="uq_application_per_job"),
        ]

    def __str__(self):
        return f"{self.applicant} -> {self.opportunity}"


class ApplicationAnswer(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="answers")
    requirement = models.ForeignKey(
        ApplicationRequirement, on_delete=models.SET_NULL, null=True, blank=True, related_name="answers",
    )
    # Copied from the requirement so the answer still reads correctly if
    # the requirement is later edited or removed.
    label = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=ApplicationRequirement.Kind.choices)
    value = models.TextField(blank=True)
    file = models.FileField(upload_to=application_file_path, storage=application_storage, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["pk"]



class ExportLog(models.Model):
    """A team member downloaded or printed a job's applicant list. Personal
    data leaving the site is recorded: who, which job, how many people."""

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        PRINT = "print", "Printable list"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="exports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    user_name = models.CharField(max_length=120)
    opportunity = models.ForeignKey(
        "opportunities.Opportunity", on_delete=models.SET_NULL, null=True, related_name="+",
    )
    job_title = models.CharField(max_length=300)
    format = models.CharField(max_length=10, choices=Format.choices)
    row_count = models.PositiveIntegerField()
    filters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_name} exported {self.row_count} from {self.job_title}"
