"""
Tracks *where* opportunities get auto-fetched from, *when* each source is
due next, and *what happened* each time a fetch ran.

Deliberately separate from apps.opportunities — adding a new source later
means adding one FetchSource row + (for a new kind of feed) one connector
class, never touching the core Opportunity model or moderation logic.

Scheduling lives on the row itself (fetch_interval_minutes / next_fetch_at)
so the worker needs no external scheduler: it just asks the database
"which active sources are due?" every cycle. See apps/ingestion/scheduler.py.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

# Retry quickly after a first failure, then back off — a feed that's down
# for a day shouldn't be hammered every few minutes, but a one-off timeout
# shouldn't cost a full 6-hour wait either.
FAILURE_RETRY_BASE = timedelta(minutes=15)
FAILURE_RETRY_MAX = timedelta(hours=24)


class FetchSource(models.Model):
    class ConnectorType(models.TextChoices):
        RSS = "rss", "RSS / Atom feed"
        # Company careers pages hosted by an applicant-tracking system. The
        # URL is the public board page; the connector reads the ATS's
        # public job-board API behind it (connectors/job_boards.py).
        GREENHOUSE = "greenhouse", "Greenhouse job board"
        ASHBY = "ashby", "Ashby job board"
        WORKABLE = "workable", "Workable job board"

    name = models.CharField(max_length=120)
    connector_type = models.CharField(max_length=30, choices=ConnectorType.choices)
    url = models.URLField(
        max_length=500,
        help_text="RSS/Atom feed URL, or the careers board page, e.g. https://job-boards.greenhouse.io/acme, "
                  "https://jobs.ashbyhq.com/acme, https://apply.workable.com/acme/",
    )
    # Big employers post worldwide; keep only what's relevant to our readers.
    include_keywords = models.TextField(
        blank=True, db_default="", default="",
        help_text="Comma-separated. Only keep items whose title or location mentions one of these "
                  "(e.g. 'Ghana, Nigeria, Kenya, Africa, Remote'). Blank keeps everything.",
    )

    # Every fetched opportunity needs a category — this is the default
    # applied to everything this source produces, since most feeds don't
    # self-describe into our category scheme.
    category = models.ForeignKey(
        "opportunities.OpportunityCategory", on_delete=models.PROTECT, related_name="fetch_sources"
    )

    is_active = models.BooleanField(default=True)

    # --- Automatic scheduling ---------------------------------------------
    fetch_interval_minutes = models.PositiveIntegerField(
        default=360,
        help_text="How often the worker fetches this source automatically (minutes).",
    )
    next_fetch_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the worker will fetch this source next. Empty means 'on the next cycle'.",
    )
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    last_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_active", "next_fetch_at"]),
        ]

    def __str__(self):
        return self.name

    def keywords(self) -> list[str]:
        return [k.strip().lower() for k in self.include_keywords.split(",") if k.strip()]

    def wants(self, item: dict) -> bool:
        """include_keywords filter, matched on title + location only (a
        description mentions too many places to be a useful signal)."""
        keywords = self.keywords()
        if not keywords:
            return True
        haystack = f"{item.get('title', '')} {item.get('location', '')}".lower()
        return any(k in haystack for k in keywords)

    def is_due(self, now=None) -> bool:
        now = now or timezone.now()
        return self.is_active and (self.next_fetch_at is None or self.next_fetch_at <= now)

    def schedule_next(self, succeeded: bool, error: str = "", now=None) -> None:
        """Set next_fetch_at after a run. Doesn't save — the caller saves
        with update_fields so a concurrent admin edit isn't clobbered."""
        now = now or timezone.now()
        if succeeded:
            self.consecutive_failures = 0
            self.last_error = ""
            self.next_fetch_at = now + timedelta(minutes=self.fetch_interval_minutes)
        else:
            self.consecutive_failures += 1
            self.last_error = error[:2000]
            backoff = FAILURE_RETRY_BASE * (2 ** (self.consecutive_failures - 1))
            self.next_fetch_at = now + min(backoff, FAILURE_RETRY_MAX)


class FetchLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial (some items failed)"
        FAILURE = "failure", "Failure"

    source = models.ForeignKey(FetchSource, on_delete=models.CASCADE, related_name="logs")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices)
    items_found = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["source", "-started_at"])]

    def __str__(self):
        return f"{self.source.name} @ {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
