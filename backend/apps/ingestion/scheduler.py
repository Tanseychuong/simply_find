"""
What the worker does each cycle — two jobs, both driven entirely by the
database so no Celery/Redis/cron is needed:

  1. Fetch every active source whose next_fetch_at has come due.
  2. Enrich every opportunity still waiting for its image/summary.

Both "claim" their rows before doing any network I/O: inside a short
transaction they lock due rows with SKIP LOCKED and push them forward by
a lease, then release the lock and do the slow work. That makes it safe
to run more than one worker (or a worker plus a moderator clicking
"Fetch now") without two processes fetching the same thing; a worker
that dies mid-job simply lets the lease expire and another picks it up.
"""

import logging
from datetime import timedelta

import requests
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.opportunities.models import Opportunity

from .enrichment import MAX_ATTEMPTS, enrich_opportunity
from .models import FetchSource
from .services import fetch_source

logger = logging.getLogger(__name__)

SOURCE_LEASE = timedelta(minutes=15)
ENRICH_RETRY_AFTER = timedelta(minutes=10)


def claim_due_sources(limit: int, now=None) -> list[FetchSource]:
    now = now or timezone.now()
    with transaction.atomic():
        sources = list(
            FetchSource.objects.select_for_update(skip_locked=True)
            .filter(is_active=True)
            .filter(Q(next_fetch_at__isnull=True) | Q(next_fetch_at__lte=now))
            .select_related("category")
            .order_by(F("next_fetch_at").asc(nulls_first=True), "pk")[:limit]
        )
        if sources:
            FetchSource.objects.filter(pk__in=[s.pk for s in sources]).update(next_fetch_at=now + SOURCE_LEASE)
    return sources


def run_due_sources(limit: int = 10, now=None) -> list:
    logs = []
    for source in claim_due_sources(limit, now=now):
        log = fetch_source(source)
        logger.info("Fetched %s: %s (found %s, new %s)", source.name, log.status, log.items_found, log.items_created)
        logs.append(log)
    return logs


def claim_pending_enrichment(limit: int, now=None) -> list[Opportunity]:
    now = now or timezone.now()
    with transaction.atomic():
        items = list(
            Opportunity.objects.select_for_update(skip_locked=True)
            .filter(enrichment_status=Opportunity.EnrichmentStatus.PENDING, enrichment_attempts__lt=MAX_ATTEMPTS)
            .filter(Q(enrichment_checked_at__isnull=True) | Q(enrichment_checked_at__lte=now - ENRICH_RETRY_AFTER))
            .order_by(F("enrichment_checked_at").asc(nulls_first=True), "-pk")[:limit]
        )
        if items:
            # The lease: nobody else re-claims these for ENRICH_RETRY_AFTER.
            Opportunity.objects.filter(pk__in=[o.pk for o in items]).update(enrichment_checked_at=now)
    return items


def run_pending_enrichment(limit: int = 25, now=None) -> int:
    items = claim_pending_enrichment(limit, now=now)
    if not items:
        return 0
    with requests.Session() as session:  # reuse connections across the batch
        for opportunity in items:
            try:
                enrich_opportunity(opportunity, session=session)
            except Exception:  # noqa: BLE001 — one bad page must not stop the batch
                logger.exception("Unexpected enrichment error for opportunity %s", opportunity.pk)
    return len(items)


def run_cycle(source_limit: int = 10, enrich_limit: int = 25) -> dict:
    logs = run_due_sources(limit=source_limit)
    enriched = run_pending_enrichment(limit=enrich_limit)
    return {
        "sources_fetched": len(logs),
        "opportunities_created": sum(log.items_created for log in logs),
        "opportunities_enriched": enriched,
    }
