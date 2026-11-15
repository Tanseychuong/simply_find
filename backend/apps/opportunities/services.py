"""
Business logic kept out of views.py so it's testable on its own and
reusable — e.g. the same approve()/reject() path is used whether the
action comes from the DRF API or (in admin.py) from the Django admin's
bulk actions.
"""

import re
from collections import Counter
from datetime import timedelta

from django.apps import apps
from django.db.models import Max, Q
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
    visibility rule via Opportunity.visible_to(), hides
    listings whose deadline has passed (unless include_expired), then an
    optional category filter on top."""
    queryset = Opportunity.visible_to(user).select_related("category", "posted_by", "company")
    if not include_expired:
        queryset = queryset.filter(Opportunity.open_q())
    slugs = [s for s in (category_slug or "").split(",") if s]
    if slugs:
        queryset = queryset.filter(category__slug__in=slugs)
    return queryset.order_by("-published_at", "-pk")


# ?career_level= buckets, by the most experience a listing asks for (0-2 years).
CAREER_LEVELS = {"no_experience": 0, "some_experience": 1, "early_career": 2}
# ?duration= buckets for internships, in months: (min, max), None = open-ended.
DURATIONS = {"short": (None, 3), "medium": (4, 6), "long": (7, None)}
# ?deadline= windows, in days from now.
DEADLINE_WINDOWS = {"week": 7, "month": 30}
MAX_LOCATION_TERMS = 5


def _choices(params, key, allowed):
    return [v for v in params.get(key, "").split(",") if v in allowed]


def filter_by_role(queryset, params):
    """The feed's filters, from query parameters. Lists are comma-separated
    and match any of their values; unknown values are ignored.

    ?role_type=internship,entry_level   ?work_mode=remote   ?paid=true
    ?employment_type=full_time,part_time
    ?graduation_year=2026        roles open to that graduation year
    ?career_level=no_experience,some_experience,early_career
                                 0, 1 or 2 years of experience asked for
    ?deadline=week|month|rolling closing within 7 / 30 days, or no deadline
    ?posted_within=7             published in the last N days (1-365)
    ?location=Ghana,Kenya        location contains any of the terms (max 5)
    ?duration=short,medium,long  internships of up to 3, 4-6, or 7+ months
    ?apply_on_site=true          apply on SimplyFind with your documents
    ?verified=true               posted by a verified company
    ?open_to_minors=true         accepts applicants under 18"""
    role_types = _choices(params, "role_type", Opportunity.RoleType.values)
    if role_types:
        queryset = queryset.filter(role_type__in=role_types)
    else:
        # Graduate school listings are an opt-in tab, not part of the job feed.
        queryset = queryset.exclude(role_type=Opportunity.RoleType.GRADUATE_SCHOOL)
    work_modes = _choices(params, "work_mode", Opportunity.WorkMode.values)
    if work_modes:
        queryset = queryset.filter(work_mode__in=work_modes)
    employment_types = _choices(params, "employment_type", Opportunity.EmploymentType.values)
    if employment_types:
        queryset = queryset.filter(employment_type__in=employment_types)
    if params.get("paid") == "true":
        queryset = queryset.filter(is_paid=True)
    year = params.get("graduation_year", "")
    if year.isdigit():
        year = int(year)
        queryset = queryset.filter(
            Q(graduation_year_min__isnull=True) | Q(graduation_year_min__lte=year),
            Q(graduation_year_max__isnull=True) | Q(graduation_year_max__gte=year),
        )

    levels = _choices(params, "career_level", CAREER_LEVELS)
    if levels:
        queryset = queryset.filter(experience_years_max__in=[CAREER_LEVELS[v] for v in levels])

    now = timezone.now()
    deadline = params.get("deadline", "")
    if deadline in DEADLINE_WINDOWS:
        # The feed already hides closed listings; this narrows to the window.
        queryset = queryset.filter(application_deadline__lte=now + timedelta(days=DEADLINE_WINDOWS[deadline]))
    elif deadline == "rolling":
        queryset = queryset.filter(application_deadline__isnull=True)

    posted = params.get("posted_within", "")
    if posted.isdigit() and 1 <= int(posted) <= 365:
        queryset = queryset.filter(published_at__gte=now - timedelta(days=int(posted)))

    terms = [t.strip() for t in params.get("location", "").split(",") if t.strip()][:MAX_LOCATION_TERMS]
    if terms:
        match = Q()
        for term in terms:
            match |= Q(location__icontains=term[:100])
        queryset = queryset.filter(match)

    durations = _choices(params, "duration", DURATIONS)
    if durations:
        match = Q()
        for key in durations:
            low, high = DURATIONS[key]
            bucket = Q(duration_months__isnull=False)
            if low is not None:
                bucket &= Q(duration_months__gte=low)
            if high is not None:
                bucket &= Q(duration_months__lte=high)
            match |= bucket
        queryset = queryset.filter(match)

    if params.get("apply_on_site") == "true":
        queryset = queryset.filter(application_method=Opportunity.ApplicationMethod.IN_APP)
    if params.get("verified") == "true":
        queryset = queryset.filter(company__is_verified=True)
    if params.get("open_to_minors") == "true":
        queryset = queryset.filter(accepts_minors=True)
    return queryset


def _place(location: str) -> str:
    """The broadest part of a free-text location: "Accra, Ghana (hybrid)" -> "Ghana"."""
    last = location.split(",")[-1]
    return re.sub(r"\(.*?\)", "", last).strip(" .-")


def live_locations(user, limit: int = 40) -> list[dict]:
    """Places with open roles, busiest first, for the location filter's
    suggestions: [{"name": "Ghana", "count": 12}, ...]. Countries (or cities
    when that is all a listing gives) from the open listings' locations."""
    counts = Counter()
    labels = {}
    rows = (
        list_visible_opportunities(user).order_by().exclude(location="")
        .filter(role_type__in=[t for t in Opportunity.RoleType.values if t != Opportunity.RoleType.GRADUATE_SCHOOL])
        .values_list("location", flat=True)
    )
    for location in rows:
        place = _place(location)
        if not place or len(place) > 60:
            continue
        key = place.casefold()
        counts[key] += 1
        labels.setdefault(key, place)
    return [{"name": labels[k], "count": n} for k, n in counts.most_common(limit)]


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
