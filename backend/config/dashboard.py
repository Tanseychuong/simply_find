"""
Numbers and short lists for the admin home page (templates/admin/index.html).

Each section is only computed for staff who can view that model, so a
moderator who can't see users never gets user counts. "Live" uses the
same rule as the public feed: what an anonymous visitor can open right now.
"""

from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.timesince import timesince

from apps.accounts.models import User
from apps.analytics.services import visitor_stats
from apps.ingestion.models import FetchLog, FetchSource
from apps.opportunities.models import Opportunity, OpportunityCategory, SavedOpportunity
from apps.opportunities.services import list_visible_opportunities

CHART_DAYS = 14


def _with_age(rows, field, now):
    """Attach a short '3 days' / '5 hours' age for the list pills."""
    rows = list(rows)
    for row in rows:
        row.age = timesince(getattr(row, field), now, depth=1)
    return rows


def _daily_published(now):
    start = (now - timedelta(days=CHART_DAYS - 1)).date()
    counts = dict(
        Opportunity.objects.filter(status=Opportunity.Status.APPROVED, published_at__date__gte=start)
        .annotate(day=TruncDate("published_at"))
        .values_list("day")
        .annotate(n=Count("id"))
    )
    days = [start + timedelta(days=i) for i in range(CHART_DAYS)]
    peak = max(counts.values(), default=0) or 1
    return [{"day": d, "count": counts.get(d, 0), "pct": round(counts.get(d, 0) * 100 / peak)} for d in days]


def dashboard_context(request) -> dict:
    user = request.user
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    dash = {}

    if user.has_perm("opportunities.view_opportunity"):
        pending = Opportunity.objects.filter(status=Opportunity.Status.PENDING)
        live = list_visible_opportunities(None).order_by()
        per_category = list(
            OpportunityCategory.objects.filter(is_active=True)
            .annotate(n=Count("opportunities", filter=Opportunity.visibility_q(None, prefix="opportunities__")
                              & Opportunity.open_q(prefix="opportunities__")))
            .order_by("-n", "name")
            .values("name", "n")
        )
        top = max((c["n"] for c in per_category), default=0) or 1
        for c in per_category:
            c["pct"] = round(c["n"] * 100 / top)

        dash.update(
            pending_count=pending.count(),
            pending=_with_age(pending.select_related("category").order_by("submitted_at")[:6], "submitted_at", now),
            live_count=live.count(),
            added_week=live.filter(published_at__gte=week_ago).count(),
            closing=live.filter(application_deadline__isnull=False, application_deadline__lte=now + timedelta(days=14))
            .order_by("application_deadline")[:5],
            per_category=per_category,
            daily=_daily_published(now),
            enrich_waiting=Opportunity.objects.filter(enrichment_status=Opportunity.EnrichmentStatus.PENDING).count(),
            can_moderate=user.has_perm("opportunities.can_verify_opportunity"),
        )

    if user.has_perm("accounts.view_user"):
        dash["users"] = User.objects.aggregate(
            total=Count("id"),
            new_week=Count("id", filter=Q(created_at__gte=week_ago)),
            premium=Count("id", filter=Q(is_premium=True) & (Q(premium_expires_at__isnull=True) | Q(premium_expires_at__gt=now))),
        )

    if user.has_perm("opportunities.view_savedopportunity"):
        dash["saves"] = SavedOpportunity.objects.count()

    if user.has_perm("ingestion.view_fetchsource"):
        active = FetchSource.objects.filter(is_active=True)
        dash["sources"] = {
            "active": active.count(),
            "failing": active.filter(consecutive_failures__gt=0).order_by("-consecutive_failures")[:4],
            "next_due": active.order_by("next_fetch_at").values_list("next_fetch_at", flat=True).first(),
        }
    if user.has_perm("ingestion.view_fetchlog"):
        dash["logs"] = _with_age(FetchLog.objects.select_related("source")[:5], "started_at", now)

    if user.has_perm("analytics.view_pageview"):
        dash["visitors"] = visitor_stats(now)

    dash["my_actions"] = _with_age(
        LogEntry.objects.filter(user=user).select_related("content_type")[:6], "action_time", now
    )
    return {"dash": dash, "now": now}
