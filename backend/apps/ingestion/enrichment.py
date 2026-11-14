"""
Per-opportunity enrichment: visit each listing's own page and pull its
Open Graph / meta tags — cover image, summary, organisation name — the
same data a chat app uses to draw a link preview — plus, when the source
gave none, the description's sections from the page's own headings
(Eligibility, Benefits, How to apply …; see sections.py).

Runs automatically from the worker for every opportunity that has a URL,
fetched or user-submitted. Rules that keep it safe to run unattended:

  * It only ever FILLS blanks. A title, description, organisation or image
    that a person (or the feed) already provided is never overwritten.
  * It writes with update_fields, so it can't clobber a moderator who
    approves/rejects the same row at the same moment.
  * Network failures retry a few times (spaced out by the scheduler);
    links that can never work (unsafe hosts, PDFs) are marked SKIPPED.

One exception to "only fills blanks", for listings fetched from an
aggregator's feed (listing_url set): the link a learner clicks should be
the organiser's, not the aggregator's write-up. While the URL is still
the one the feed gave us, it's replaced by the organiser link found in
the article (organizer.py), and the organisation name comes from the
organiser's site — the aggregator's og:site_name never names it. The
organiser's home page also supplies "About the organisation" when the
article has no such section. If that
link is already on another listing (two aggregators posted the same
call), this copy is rejected as a duplicate while it's still pending.
"""

import logging
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from django.db.models import Q
from django.utils import timezone

from apps.opportunities.models import Opportunity
from apps.opportunities.sections import as_text, clean_sections

from .classify import find_deadline
from .http import NotFetchableError, fetch_public_html
from .organizer import find_organizer_url, site_domain
from .sections import extract_sections

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MIN_USEFUL_DESCRIPTION = 40  # shorter than this and the page's summary is better
MIN_ORG_SUMMARY, MAX_ORG_SUMMARY = 60, 600  # a home page's meta description, as "About the organisation"
SAME_TITLE_RATIO = 0.6  # "Stanton Fellows Program 2027" ~ "Stanton Fellows Program 2027/2028 (Funded)"

# Hosted application forms and applicant-tracking systems: their site name
# is the software's ("Workable", "Jotform"), not the organiser's.
APPLICATION_PLATFORMS = {
    "greenhouse.io", "ashbyhq.com", "workable.com", "lever.co", "smartrecruiters.com", "myworkdayjobs.com",
    "bamboohr.com", "recruitee.com", "breezy.hr", "icims.com", "taleo.net", "successfactors.com",
    "successfactors.eu", "dvinci-easy.com", "hr-manager.net", "jotform.com", "typeform.com", "google.com",
    "forms.gle", "office.com", "microsoft.com", "surveymonkey.com", "submittable.com", "fluxx.io",
    "smapply.io", "zohorecruit.com", "applytojob.com", "jobvite.com", "teamtailor.com", "personio.de",
    "fillout.com", "accubate.app", "oraclecloud.com", "myworkdaysite.com", "formstack.com", "wufoo.com",
    "cognitoforms.com", "airtable.com", "tally.so", "eightfold.ai", "paylocity.com", "ultipro.com",
}


class _StopParsing(Exception):
    pass


class _MetaParser(HTMLParser):
    """Collects <meta> tags and <title> from the document head, then stops."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            raise _StopParsing
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").strip().lower()
            content = (attrs.get("content") or "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            raise _StopParsing

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)


def extract_metadata(html: str, base_url: str) -> dict:
    parser = _MetaParser()
    try:
        parser.feed(html)
        parser.close()
    except _StopParsing:
        pass

    meta = parser.meta

    def first(*keys):
        for key in keys:
            value = meta.get(key)
            if value:
                return " ".join(unescape(value).split())
        return ""

    image = first("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src")
    if image:
        image = urljoin(base_url, image)
        if urlparse(image).scheme not in ("http", "https") or len(image) > 1000:
            image = ""

    return {
        "image_url": image,
        "description": first("og:description", "description", "twitter:description")[:2000],
        "site_name": first("og:site_name", "application-name")[:200],
        "title": (first("og:title", "twitter:title") or " ".join("".join(parser.title_parts).split()))[:200],
    }


def enrich_opportunity(opportunity: Opportunity, session: requests.Session | None = None) -> str:
    """Enrich one opportunity in place; returns the resulting status."""
    now = timezone.now()
    changed = {"enrichment_checked_at": now}

    # An aggregator's article is the page with the write-up (sections, image,
    # the organiser's link), even after opportunity_url points elsewhere.
    page_url = opportunity.listing_url or opportunity.opportunity_url
    if not page_url:
        changed["enrichment_status"] = Opportunity.EnrichmentStatus.SKIPPED
        return _save(opportunity, changed)

    try:
        html, final_url = fetch_public_html(page_url, session=session)
    except NotFetchableError as exc:
        logger.info("Enrichment skipped for opportunity %s: %s", opportunity.pk, exc)
        changed["enrichment_status"] = Opportunity.EnrichmentStatus.SKIPPED
        return _save(opportunity, changed)
    except requests.RequestException as exc:
        attempts = opportunity.enrichment_attempts + 1
        changed["enrichment_attempts"] = attempts
        changed["enrichment_status"] = (
            Opportunity.EnrichmentStatus.FAILED if attempts >= MAX_ATTEMPTS
            else Opportunity.EnrichmentStatus.PENDING
        )
        logger.warning("Enrichment attempt %s failed for opportunity %s: %s", attempts, opportunity.pk, exc)
        return _save(opportunity, changed)

    meta = extract_metadata(html, final_url)
    if meta["image_url"] and not opportunity.image_url:
        changed["image_url"] = meta["image_url"]
    if meta["description"] and len(opportunity.description.strip()) < MIN_USEFUL_DESCRIPTION:
        changed["description"] = meta["description"]

    # Sections from the page's own headings, when the source didn't give any.
    sections = opportunity.sections or extract_sections(html, page=True)

    resolved_now = ""
    if opportunity.listing_url:
        # Still the URL the feed gave us? Then look for the organiser's link.
        # Otherwise it was resolved before (or a moderator set it) — keep it.
        organizer_url = ""
        if opportunity.opportunity_url == opportunity.listing_url:
            feed_url = opportunity.fetch_source.url if opportunity.fetch_source_id else ""
            organizer_url = resolved_now = find_organizer_url(
                html, final_url, also_ignore=(opportunity.listing_url, feed_url),
            )
            if organizer_url:
                changed["opportunity_url"] = organizer_url
        else:
            organizer_url = opportunity.opportunity_url
        # Earlier enrichment runs filled organisation from the aggregator's
        # own site name; that's wrong, so it doesn't count as set.
        wrong_org = bool(meta["site_name"]) and opportunity.organization == meta["site_name"]
        needs_name = not opportunity.organization or wrong_org
        needs_summary = not any(s["kind"] == "organization" for s in sections)
        profile = (
            _organizer_profile(organizer_url, session)
            if organizer_url and (needs_name or needs_summary) else {"name": "", "summary": ""}
        )
        if needs_name and (profile["name"] or wrong_org):
            changed["organization"] = profile["name"]
        if needs_summary and profile["summary"]:
            sections = clean_sections([
                *sections,
                {"kind": "organization", "blocks": [{"type": "p", "text": profile["summary"]}]},
            ])
    elif meta["site_name"] and not opportunity.organization:
        changed["organization"] = meta["site_name"]

    if sections != opportunity.sections:
        changed["sections"] = sections
        if not opportunity.application_deadline:
            deadline = find_deadline(as_text(sections))
            if deadline:
                changed["application_deadline"] = deadline

    changed["enrichment_status"] = Opportunity.EnrichmentStatus.DONE
    status = _save(opportunity, changed)
    if resolved_now:
        _reject_if_duplicate(opportunity, resolved_now)
    return status


def _organizer_profile(url: str, session: requests.Session | None) -> dict:
    """The organiser's name and one-paragraph summary, from their site's
    home page (og:site_name and meta description) — the page about the
    organisation, not about this one opportunity. Best effort, never fatal."""
    nothing = {"name": "", "summary": ""}
    domain = site_domain(url)
    if not domain or domain in APPLICATION_PLATFORMS:
        return nothing
    home = f"{urlparse(url).scheme or 'https'}://{domain}/"
    try:
        html, final_url = fetch_public_html(home, session=session)
    except (NotFetchableError, requests.RequestException) as exc:
        logger.info("Couldn't read organiser home page %s: %s", home, exc)
        return nothing
    if site_domain(final_url) in APPLICATION_PLATFORMS:
        return nothing
    meta = extract_metadata(html, final_url)
    summary = meta["description"] if len(meta["description"]) >= MIN_ORG_SUMMARY else ""
    return {"name": meta["site_name"], "summary": summary[:MAX_ORG_SUMMARY]}


def _same_title(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SAME_TITLE_RATIO


def _reject_if_duplicate(opportunity: Opportunity, organizer_url: str) -> None:
    """Same organiser link alone isn't enough: one source often points
    several jobs at a shared form or careers page. A duplicate is the same
    link, from a different source, under a near-identical title."""
    if opportunity.source_type != Opportunity.SourceType.FETCHED:
        return
    others = (
        Opportunity.objects.filter(Q(opportunity_url=organizer_url) | Q(listing_url=organizer_url))
        .exclude(pk=opportunity.pk).order_by("pk")
    )
    if opportunity.fetch_source_id:
        others = others.exclude(fetch_source_id=opportunity.fetch_source_id)
    original = next((o for o in others.only("pk", "title")[:20] if _same_title(o.title, opportunity.title)), None)
    if original is None:
        return
    # A conditional update, not save(): if a moderator has already decided
    # on this row, leave their decision alone.
    rejected = Opportunity.objects.filter(pk=opportunity.pk, status=Opportunity.Status.PENDING).update(
        status=Opportunity.Status.REJECTED,
        reviewed_at=timezone.now(),
        rejection_reason=f"Automatic: duplicate of #{original.pk} (same organiser link, posted by another source).",
    )
    if rejected:
        opportunity.refresh_from_db(fields=["status", "reviewed_at", "rejection_reason"])


def _save(opportunity: Opportunity, changed: dict) -> str:
    for field, value in changed.items():
        setattr(opportunity, field, value)
    opportunity.save(update_fields=list(changed))
    return opportunity.enrichment_status
