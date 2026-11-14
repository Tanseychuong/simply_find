"""
Business logic kept out of views.py so it's testable on its own and
reusable — e.g. the same approve()/reject() path is used whether the
action comes from the DRF API or (in admin.py) from the Django admin's
bulk actions.
"""

from datetime import timedelta

from django.apps import apps
from django.db.models import Max
from django.utils import timezone

from .models import Opportunity


def submit_opportunity(user, validated_data) -> Opportunity:
    """A user submits a new opportunity — always starts PENDING regardless
    of who's submitting, admins included, since even an admin's submission
    should go through the same visible moderation trail."""
    return Opportunity.objects.create(
        posted_by=user,
        source_type=Opportunity.SourceType.SUBMITTED,
        status=Opportunity.Status.PENDING,
        **validated_data,
    )


def approve_opportunity(opportunity: Opportunity, reviewer) -> Opportunity:
    opportunity.approve(reviewer)
    return opportunity


def reject_opportunity(opportunity: Opportunity, reviewer, reason: str) -> Opportunity:
    was_live = opportunity.status == Opportunity.Status.APPROVED
    opportunity.reject(reviewer, reason)
    if was_live:
        from config.seo import request_site_rebuild
        request_site_rebuild(f"listing {opportunity.pk} taken down")
    return opportunity


def list_visible_opportunities(user, category_slug: str | None = None, include_expired: bool = False):
    """The one place list endpoints get their queryset from — applies the
    premium/free visibility rule via Opportunity.visible_to(), hides
    listings whose deadline has passed (unless include_expired), then an
    optional category filter on top."""
    queryset = Opportunity.visible_to(user).select_related("category", "posted_by", "company")
    if not include_expired:
        queryset = queryset.filter(Opportunity.open_q())
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)
    return queryset.order_by("-published_at", "-pk")


def landing_stats(user) -> dict:
    """Headline numbers for the public landing page. Counted with the same
    visibility rule as the feed, so the page never advertises listings the
    visitor can't actually open."""
    FetchSource = apps.get_model("ingestion", "FetchSource")  # no hard import: ingestion depends on us

    # .order_by() clears the feed ordering — otherwise DISTINCT would also
    # be applied to published_at and over-count organizations/categories.
    live = list_visible_opportunities(user).order_by()
    week_ago = timezone.now() - timedelta(days=7)
    return {
        "live": live.count(),
        "added_this_week": live.filter(published_at__gte=week_ago).count(),
        "organizations": live.exclude(organization="").values("organization").distinct().count(),
        "categories": live.values("category").distinct().count(),
        "sources": FetchSource.objects.filter(is_active=True).count(),
        "last_fetched_at": FetchSource.objects.aggregate(latest=Max("last_fetched_at"))["latest"],
    }
