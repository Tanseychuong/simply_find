"""
RSS 2.0 and Atom connector, standard library only.

Every item comes back as a plain dict (see connectors/base.py). Notes on
the mapping, because feeds are messy:

  * pubDate / published / updated is when the SOURCE published the item.
    It goes to `source_published_at` — not `application_deadline`. Feeds
    almost never carry a real deadline; treating the publish date as one
    made every fetched listing look expired the moment it arrived.
  * Descriptions are usually HTML. Tags are stripped and entities decoded
    so the frontend never shows raw markup. When a feed carries the whole
    article (<content:encoded>), the short <description> is the summary
    and the article's headings become `sections` (ingestion/sections.py).
  * <category> tags come back as `categories`; services.py uses them to
    file an aggregator's items under the right OpportunityCategory.
  * Images come from <enclosure type="image/*">, <media:content> or
    <media:thumbnail> when present; otherwise enrichment finds one later
    from the listing page itself.
"""

import re
from datetime import datetime
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree

import requests
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags

from ..http import TIMEOUT, default_headers
from ..sections import extract_sections
from .base import BaseConnector

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

MAX_FEED_BYTES = 5_000_000
MAX_DESCRIPTION = 5000


class RSSConnector(BaseConnector):
    def fetch(self) -> list[dict]:
        response = requests.get(
            self.source.url,
            timeout=TIMEOUT,
            headers=default_headers("application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"),
        )
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError(f"Feed is larger than {MAX_FEED_BYTES // 1_000_000} MB")

        if response.content.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError(
                "This URL returned a web page, not an RSS/Atom feed. Use the site's feed URL "
                "(often <site>/feed/), or a job-board connector for a careers page."
            )
        root = ElementTree.fromstring(response.content)
        entries = root.findall(".//item")
        if entries:
            return [item for item in (self._parse_rss_item(el) for el in entries) if item]
        return [item for item in (self._parse_atom_entry(el) for el in root.iter(f"{ATOM}entry")) if item]

    # --- RSS 2.0 -------------------------------------------------------------

    def _parse_rss_item(self, el) -> dict | None:
        title = clean_text(_text(el, "title"))
        if not title:
            return None  # nothing usable without at least a title
        article = _text(el, f"{CONTENT}encoded")
        description = _text(el, "description") or article
        return {
            "title": title,
            "description": clean_summary(description),
            "sections": extract_sections(article or description),
            "opportunity_url": _text(el, "link").strip(),
            # Always blank: the feed's name is the aggregator's and
            # <dc:creator> is whoever wrote the post. Enrichment fills it
            # from the organiser's own site (enrichment.py).
            "organization": "",
            "source_published_at": _parse_date(_text(el, "pubDate")),
            "image_url": _rss_image(el),
            "categories": [clean_text(c.text) for c in el.findall("category") if c.text],
        }

    # --- Atom ----------------------------------------------------------------

    def _parse_atom_entry(self, el) -> dict | None:
        title = clean_text(_text(el, f"{ATOM}title"))
        if not title:
            return None
        link = ""
        for link_el in el.findall(f"{ATOM}link"):
            if link_el.get("rel", "alternate") == "alternate" and link_el.get("href"):
                link = link_el.get("href").strip()
                break
        description = _text(el, f"{ATOM}content") or _text(el, f"{ATOM}summary")
        return {
            "title": title,
            "description": clean_summary(_text(el, f"{ATOM}summary") or description),
            "sections": extract_sections(description),
            "opportunity_url": link,
            "organization": "",  # <author> is the post's writer, as with RSS
            "source_published_at": _parse_date(_text(el, f"{ATOM}published") or _text(el, f"{ATOM}updated")),
            "image_url": _rss_image(el),
            "categories": [c.get("term", "") for c in el.findall(f"{ATOM}category") if c.get("term")],
        }


# WordPress appends this to every feed excerpt: "The post X appeared first on Y."
_POSTED_FIRST = re.compile(r"\s*The post .{0,300}? appeared first on .{0,120}?\.?\s*$", re.DOTALL)


def clean_summary(raw: str) -> str:
    return _POSTED_FIRST.sub("", clean_text(raw))[:MAX_DESCRIPTION]


def clean_text(raw: str) -> str:
    """HTML fragment -> plain text with normalised whitespace."""
    if not raw:
        return ""
    return " ".join(unescape(strip_tags(raw)).split())


def _text(el, tag: str) -> str:
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _rss_image(el) -> str:
    for enclosure in el.findall("enclosure"):
        if (enclosure.get("type") or "").startswith("image/") and enclosure.get("url"):
            return enclosure.get("url").strip()
    for tag in (f"{MEDIA}content", f"{MEDIA}thumbnail"):
        for media in el.iter(tag):
            url = media.get("url")
            medium = media.get("medium", "image")
            mime = media.get("type", "image/")
            if url and (medium == "image" or mime.startswith("image/")):
                return url.strip()
    return ""


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    parsed = None
    try:
        parsed = parsedate_to_datetime(raw)     # RSS: "Mon, 01 Jan 2026 00:00:00 GMT"
    except (TypeError, ValueError):
        try:
            parsed = parse_datetime(raw)        # Atom: "2026-01-01T00:00:00Z"
        except ValueError:
            parsed = None
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed
