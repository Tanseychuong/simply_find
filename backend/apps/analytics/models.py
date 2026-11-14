"""
First-party visitor analytics: who comes, how often they come back, and
where they arrive from.

A visitor is one browser, identified by a random id the frontend keeps in
localStorage. A *visit* is a run of page views with no gap longer than
VISIT_GAP; the page view that opens a visit records where the visitor
came from. Each page view also keeps the IP address and country as a
security log, erased after IP_RETENTION (see services.prune_old_data).
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

VISIT_GAP = timedelta(minutes=30)  # the usual analytics rule for "a new visit"
DIRECT = "Direct"


class Visitor(models.Model):
    id = models.UUIDField(primary_key=True)
    first_seen = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)
    visit_count = models.PositiveIntegerField(default=0)
    first_source = models.CharField(max_length=100, blank=True, help_text="Where their very first visit came from.")
    # Set once a logged-in member is seen on this browser.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="visitors",
    )

    class Meta:
        ordering = ("-last_seen",)

    def __str__(self):
        return str(self.id)[:8]


class PageView(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="page_views")
    path = models.CharField(max_length=300)
    starts_visit = models.BooleanField(default=False)
    # Only filled on the page view that starts a visit: a referring site
    # ("google.com"), a utm_source tag, or "Direct".
    source = models.CharField(max_length=100, blank=True, db_index=True)
    # Security log, for investigating abuse or an incident. Erased after
    # services.IP_RETENTION; the rest of the row is kept for the stats.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=2, blank=True, help_text="ISO country code, when the host provides one.")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.path} @ {self.created_at:%Y-%m-%d %H:%M}"
