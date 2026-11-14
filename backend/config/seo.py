"""
/sitemap.xml for search engines: every public page on the frontend
(SITE_URL), built from live data so new listings and companies are found
within the cache window. robots.txt on the frontend points here.
"""

import logging
from xml.sax.saxutils import escape

import requests
from django.conf import settings
from django.db import transaction
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

SITEMAP_CACHE_KEY = "seo:sitemap"
SITEMAP_CACHE_SECONDS = 60 * 60
MAX_URLS = 45000  # the protocol's limit is 50,000 per file


def _url(path, lastmod=None, changefreq=None, priority=None):
    parts = [f"<loc>{escape(settings.SITE_URL + path)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod.date().isoformat()}</lastmod>")
    if changefreq:
        parts.append(f"<changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"<priority>{priority}</priority>")
    return "<url>" + "".join(parts) + "</url>"


def build_sitemap() -> str:
    from apps.companies.models import Company
    from apps.opportunities.models import Opportunity, OpportunityCategory

    now = timezone.now()
    urls = [
        _url("/", now, "daily", "1.0"),
        _url("/opportunities", now, "hourly", "0.9"),
        _url("/companies/join", None, "monthly", "0.6"),
        _url("/privacy", None, "yearly", "0.2"),
    ]
    for slug in OpportunityCategory.objects.filter(is_active=True).values_list("slug", flat=True):
        urls.append(_url(f"/opportunities?category={slug}", now, "daily", "0.8"))
    for slug, updated in Company.objects.filter(status=Company.Status.APPROVED).values_list("slug", "updated_at"):
        urls.append(_url(f"/companies/{slug}", updated, "weekly", "0.6"))

    # What an anonymous visitor (and so a crawler) can open, still open.
    listings = (
        Opportunity.visible_to(None).filter(Opportunity.open_q())
        .order_by("-published_at").values_list("pk", "published_at")[: MAX_URLS - len(urls)]
    )
    for pk, published in listings:
        urls.append(_url(f"/opportunities/{pk}", published, "weekly", "0.7"))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )


def sitemap(request):
    xml = cache.get(SITEMAP_CACHE_KEY)
    if xml is None:
        xml = build_sitemap()
        cache.set(SITEMAP_CACHE_KEY, xml, SITEMAP_CACHE_SECONDS)
    response = HttpResponse(xml, content_type="application/xml")
    response["Cache-Control"] = f"public, max-age={SITEMAP_CACHE_SECONDS}"
    return response


def request_site_rebuild(reason: str) -> None:
    """Ask the frontend host to rebuild, so pre-rendered pages for content that
    was just taken down (suspended company, rejected listing) disappear now
    rather than at the next scheduled rebuild. Needs FRONTEND_DEPLOY_HOOK (the
    same Render deploy hook URL the ingest workflow uses); does nothing without
    it. Never raises: a failed rebuild must not undo the moderation action."""
    cache.delete(SITEMAP_CACHE_KEY)
    hook = getattr(settings, "FRONTEND_DEPLOY_HOOK", "")
    if not hook:
        return

    def fire():
        try:
            requests.post(hook, timeout=10).raise_for_status()
            logger.info("Requested a site rebuild: %s", reason)
        except requests.RequestException:
            logger.exception("Site rebuild request failed (%s)", reason)

    transaction.on_commit(fire)
