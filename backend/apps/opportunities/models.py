"""
Core domain models for the opportunity portal.

Both user-submitted and auto-fetched opportunities are rows in this same
Opportunity table (source_type tells them apart) — one moderation queue,
one set of visibility rules, regardless of where a listing came from.

The can_verify_opportunity permission (Meta.permissions below) is what
lets a non-admin user approve/reject — granted via a "Moderators" Group in
Django admin, not a field on User. See docs/opportunities.md.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

class OpportunityCategory(models.Model):
    """Admin-manageable, not an enum, so new categories don't need a code
    change — same reasoning as the Flask version."""

    slug = models.SlugField(unique=True)          # 'jobs', 'scholarships'
    name = models.CharField(max_length=120)         # 'Jobs & Internships'
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "opportunity categories"
        indexes = [models.Index(fields=["is_active"])]

    def __str__(self):
        return self.name


class Opportunity(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class SourceType(models.TextChoices):
        SUBMITTED = "submitted", "User submitted"
        FETCHED = "fetched", "Auto-fetched"
        COMPANY = "company", "Posted by a company"

    class ApplicationMethod(models.TextChoices):
        EXTERNAL = "external", "On the organiser's site"
        IN_APP = "in_app", "In-app application"

    class EnrichmentStatus(models.TextChoices):
        PENDING = "pending", "Waiting for the worker"
        DONE = "done", "Enriched"
        FAILED = "failed", "Gave up after retries"
        SKIPPED = "skipped", "Nothing to fetch"

    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="opportunities_posted", null=True, blank=True,
        # null=True: a FETCHED opportunity has no human poster
    )
    category = models.ForeignKey(
        OpportunityCategory, on_delete=models.PROTECT, related_name="opportunities"
    )

    title = models.CharField(max_length=200)
    organization = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    # The description broken into named sections — About the organisation,
    # Eligibility, Benefits, How to apply … (shape and rules in sections.py).
    # Empty means the plain description is all there is.
    sections = models.JSONField(
        default=list, blank=True,
        help_text='List of {"kind", "title", "blocks": [{"type": "p"|"li"|"h", "text"}]}. '
                  "Kinds: overview, organization, eligibility, responsibilities, benefits, documents, "
                  "how_to_apply, dates, other.",
    )
    location = models.CharField(max_length=200, blank=True)
    # Indexed: ingestion de-duplicates on this on every fetched item.
    opportunity_url = models.URLField(max_length=500, blank=True, db_index=True)
    # For listings fetched from an aggregator's feed: the aggregator's
    # article it came from. opportunity_url starts out the same and is
    # swapped for the organiser's own link once enrichment finds it
    # (apps/ingestion/organizer.py); this keeps the original for
    # de-duplication and so moderators can see where it was posted.
    listing_url = models.URLField(max_length=500, blank=True, db_index=True)
    application_deadline = models.DateTimeField(null=True, blank=True)

    # --- Automatic enrichment ---------------------------------------------
    # Filled by the ingestion worker from the listing page's Open Graph
    # metadata (apps/ingestion/enrichment.py) — for fetched AND submitted
    # opportunities. Never overwrites a value a person already provided.
    image_url = models.URLField(max_length=1000, blank=True)
    enrichment_status = models.CharField(
        max_length=10, choices=EnrichmentStatus.choices, default=EnrichmentStatus.PENDING,
    )
    enrichment_attempts = models.PositiveSmallIntegerField(default=0)
    enrichment_checked_at = models.DateTimeField(null=True, blank=True)
    # When the original source published it (e.g. an RSS pubDate) — kept
    # separate from application_deadline, which is a different thing.
    source_published_at = models.DateTimeField(null=True, blank=True)

    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, default=SourceType.SUBMITTED
    )
    # Set only for FETCHED opportunities — nullable FK to avoid a circular
    # import with the ingestion app (opportunities shouldn't have to know
    # ingestion's internals beyond "which source did this come from").
    fetch_source = models.ForeignKey(
        "ingestion.FetchSource", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="opportunities",
    )

    # --- Company jobs (apps/companies) --------------------------------------
    # Set when an approved company posted this. String reference: companies
    # depends on opportunities, not the other way round.
    company = models.ForeignKey(
        "companies.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="opportunities",
    )
    application_method = models.CharField(
        max_length=20, choices=ApplicationMethod.choices, default=ApplicationMethod.EXTERNAL,
    )

    # --- Moderation ------------------------------------------------------
    status =models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="opportunities_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "opportunities"
        permissions = [
            ("can_verify_opportunity", "Can approve or reject opportunities"),
        ]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["application_deadline"]),
            models.Index(fields=["enrichment_status", "enrichment_checked_at"]),
        ]

    def __str__(self):
        return self.title

    def approve(self, reviewer) -> None:
        now = timezone.now()
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = now
        self.published_at = now
        self.save()

    def reject(self, reviewer, reason: str) -> None:
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def is_visible_to(self, user) -> bool:
        if self.status != self.Status.APPROVED:
            return False
        if self.company_id and self.company.status != "approved":
            return False  # suspended/rejected companies' jobs come off the site
        return self.published_at is not None and self.published_at <= timezone.now()

    @property
    def is_open(self) -> bool:
        return self.application_deadline is None or self.application_deadline >= timezone.now()

    @classmethod
    def visibility_q(cls, user, prefix: str = "", now=None) -> Q:
        """The visibility rule as a Q object, so it can be used
        both as a plain filter and inside annotations (e.g. per-category
        counts) without restating the rule. `prefix` lets a related model
        apply it, e.g. prefix="opportunities__"."""
        now = now or timezone.now()
        # Jobs from a company that has been suspended or rejected are hidden.
        company_ok = Q(**{f"{prefix}company__isnull": True}) | Q(**{f"{prefix}company__status": "approved"})
        return Q(**{f"{prefix}status": cls.Status.APPROVED, f"{prefix}published_at__lte": now}) & company_ok

    @classmethod
    def open_q(cls, prefix: str = "", now=None) -> Q:
        """Still accepting applications: no deadline, or one in the future."""
        now = now or timezone.now()
        return Q(**{f"{prefix}application_deadline__isnull": True}) | Q(
            **{f"{prefix}application_deadline__gte": now}
        )

    @classmethod
    def visible_to(cls, user):
        """Query-level visibility filter — stays index-backed instead of
        loading every row to check it in Python. Use this in every list
        view rather than filtering in a loop."""
        return cls.objects.filter(cls.visibility_q(user))


class SavedOpportunity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_opportunities"
    )
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.CASCADE, related_name="saved_by"
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-saved_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "opportunity"], name="uq_saved_user_opportunity")
        ]

    def __str__(self):
        return f"{self.user} saved {self.opportunity}"