"""
Fetch-one-source logic, kept out of the worker, the management commands
and admin.py so there's exactly one implementation of "run a source,
store what's new, record what happened, schedule the next run".

Called automatically by the worker (apps/ingestion/scheduler.py) and on
demand by a moderator clicking "Fetch now" in /admin/.
"""

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.opportunities.models import Opportunity, OpportunityCategory
from apps.opportunities.sections import as_text

from .classify import classify_role, employment_type, find_deadline, guess_field
from .connectors import get_connector_class
from .models import FetchLog

logger = logging.getLogger(__name__)


def _clip(value, length: int) -> str:
    return (value or "").strip()[:length]


def _existing(source, url: str, title: str):
    # URL is the identity of a listing. Items without one fall back to
    # "same title from the same source", so a re-fetch still can't
    # create duplicates. listing_url too: once enrichment swaps in the
    # organiser's link, the feed's URL only survives there.
    if url:
        return Opportunity.objects.filter(Q(opportunity_url=url) | Q(listing_url=url))
    return Opportunity.objects.filter(fetch_source=source, title=title)


def fetch_source(source) -> FetchLog:
    started_at = timezone.now()
    items_found = 0
    items_created = 0
    items_skipped = 0
    item_errors: list[str] = []
    error_message = ""
    log_status = FetchLog.Status.SUCCESS

    try:
        connector = get_connector_class(source.connector_type)(source)
        items = connector.fetch()
        items_found = len(items)
        categories = {c.slug: c for c in OpportunityCategory.objects.filter(is_active=True)}

        seen: set[str] = set()
        for item in items:
            if not source.wants(item):
                continue
            title = _clip(item.get("title"), 200)
            url = _clip(item.get("opportunity_url"), 500)
            key = url or f"title:{title}"
            if not title or key in seen:
                continue
            seen.add(key)
            existing = _existing(source, url, title)
            if existing.exists():
                # Already have it — but listings fetched before sections
                # existed get them now (blanks only, like enrichment).
                if item.get("sections"):
                    existing.filter(sections=[]).update(sections=item["sections"])
                continue

            description = (item.get("description") or "").strip()
            is_feed = source.connector_type == source.ConnectorType.RSS
            role = classify_role(
                {**item, "sections_text": as_text(item.get("sections"))}, source.role_type,
            )
            if role is None:
                items_skipped += 1  # not a student or recent-graduate role
                continue
            try:
                # A savepoint per item: one malformed entry shouldn't
                # roll back the rest of the batch.
                with transaction.atomic():
                    Opportunity.objects.create(
                        title=title,
                        description=description or title,
                        organization=_clip(item.get("organization"), 200),
                        location=_clip(item.get("location"), 200),
                        opportunity_url=url,
                        # Feeds are aggregators: their link is the write-up,
                        # not the organiser. Job boards link straight to the
                        # employer's posting, so there's nothing to resolve.
                        listing_url=url if is_feed else "",
                        image_url=_clip(item.get("image_url"), 1000),
                        sections=item.get("sections") or [],
                        application_deadline=(
                            item.get("application_deadline") or find_deadline(description)
                            or find_deadline(as_text(item.get("sections")))
                        ),
                        source_published_at=item.get("source_published_at"),
                        category=guess_field(item, source.category, categories),
                        role_type=role.role_type,
                        experience_years_max=role.experience_years,
                        employment_type=employment_type(
                            f"{title} {item.get('location') or ''} {description} {as_text(item.get('sections'))}"
                        ),
                        source_type=Opportunity.SourceType.FETCHED,
                        status=Opportunity.Status.PENDING,  # fetched never means approved
                        fetch_source=source,
                    )
                items_created += 1
            except Exception as exc:  # noqa: BLE001 — record and keep going
                item_errors.append(f"{title[:60]}: {exc}")

        if item_errors:
            log_status = FetchLog.Status.PARTIAL
            error_message = f"{len(item_errors)} item(s) failed: " + "; ".join(item_errors[:5])
        elif items_found and not items_created and items_skipped < items_found:
            log_status = FetchLog.Status.PARTIAL  # feed had items, all already known — worth knowing, not an error

    except Exception as exc:  # noqa: BLE001 — genuinely want to catch+log anything here
        log_status = FetchLog.Status.FAILURE
        error_message = str(exc)[:2000]
        logger.warning("Fetch failed for source %s (%s): %s", source.pk, source.name, exc)

    finally:
        now = timezone.now()
        source.last_fetched_at = now
        source.schedule_next(succeeded=log_status != FetchLog.Status.FAILURE, error=error_message, now=now)
        source.save(update_fields=["last_fetched_at", "next_fetch_at", "consecutive_failures", "last_error"])

    return FetchLog.objects.create(
        source=source,
        started_at=started_at,
        finished_at=timezone.now(),
        status=log_status,
        items_found=items_found,
        items_created=items_created,
        items_skipped=items_skipped,
        error_message=error_message,
    )
