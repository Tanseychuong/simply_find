"""
Company careers pages hosted by an applicant-tracking system (ATS).

Most companies don't publish an RSS feed of their jobs, but the ATS behind
their careers page exposes the same listings through a public, documented
job-board API meant for exactly this — embedding a company's openings on
another site. The FetchSource.url is the human-facing board page (what an
admin copies from the "Careers" link); each connector reads the board name
out of it and calls the API.

    Greenhouse  https://job-boards.greenhouse.io/<board>   (also boards.greenhouse.io, the EU host)
    Ashby       https://jobs.ashbyhq.com/<board>
    Workable    https://apply.workable.com/<account>/

Items are plain dicts, same keys as the RSS connector (connectors/base.py).
"""

from html import unescape
from urllib.parse import urlparse

import requests
from django.utils.dateparse import parse_date, parse_datetime

from ..http import TIMEOUT, default_headers
from ..sections import extract_sections
from .base import BaseConnector
from .rss_connector import MAX_DESCRIPTION, clean_text


def board_name(url: str) -> str:
    """The first path segment of a board URL: .../acme/jobs/123 -> 'acme'.
    Also accepts the API URLs (.../v1/boards/acme/jobs, .../accounts/acme)."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    for marker in ("boards", "accounts", "job-board"):
        if marker in parts and parts.index(marker) + 1 < len(parts):
            return parts[parts.index(marker) + 1]
    if not parts:
        raise ValueError(f"Can't find a board name in {url!r}")
    return parts[0]


def _get_json(url: str):
    response = requests.get(url, timeout=TIMEOUT, headers=default_headers("application/json"))
    response.raise_for_status()
    return response.json()


def _datetime(raw):
    if not raw:
        return None
    try:
        return parse_datetime(raw)
    except ValueError:
        return None


class GreenhouseConnector(BaseConnector):
    def fetch(self) -> list[dict]:
        board = board_name(self.source.url)
        data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        items = []
        for job in data.get("jobs", []):
            if not job.get("title"):
                continue
            content = unescape(job.get("content", ""))  # HTML that is itself entity-escaped
            items.append({
                "title": job["title"],
                "description": clean_text(content)[:MAX_DESCRIPTION],
                "sections": extract_sections(content),
                "organization": job.get("company_name") or self.source.name,
                "location": (job.get("location") or {}).get("name", ""),
                "opportunity_url": job.get("absolute_url", ""),
                "application_deadline": _datetime(job.get("application_deadline")),
                "source_published_at": _datetime(job.get("first_published") or job.get("updated_at")),
            })
        return items


class AshbyConnector(BaseConnector):
    def fetch(self) -> list[dict]:
        board = board_name(self.source.url)
        data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        items = []
        for job in data.get("jobs", []):
            if not job.get("title") or job.get("isListed") is False:
                continue
            locations = [job.get("location", "")] + [
                loc.get("location", "") for loc in job.get("secondaryLocations") or []
            ]
            items.append({
                "title": job["title"],
                "description": clean_text(job.get("descriptionPlain", ""))[:MAX_DESCRIPTION],
                "sections": extract_sections(job.get("descriptionHtml", "")),
                "organization": self.source.name,
                "location": ", ".join(loc for loc in locations if loc)
                + (" (Remote)" if job.get("isRemote") else ""),
                "opportunity_url": job.get("jobUrl", ""),
                "source_published_at": _datetime(job.get("publishedAt")),
            })
        return items


class WorkableConnector(BaseConnector):
    def fetch(self) -> list[dict]:
        account = board_name(self.source.url)
        # details=true adds each job's description (HTML) to the listing.
        data = _get_json(f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=true")
        organization = data.get("name") or self.source.name
        items = []
        for job in data.get("jobs", []):
            if not job.get("title"):
                continue
            places = [
                ", ".join(p for p in (loc.get("city"), loc.get("country")) if p)
                for loc in job.get("locations") or [{"city": job.get("city"), "country": job.get("country")}]
            ]
            published = parse_date(job["published_on"]) if job.get("published_on") else None
            items.append({
                "title": job["title"],
                "description": clean_text(job.get("description", ""))[:MAX_DESCRIPTION],
                "sections": extract_sections(job.get("description", "")),
                "organization": organization,
                "location": "; ".join(p for p in places if p) + (" (Remote)" if job.get("telecommuting") else ""),
                "opportunity_url": job.get("shortlink") or job.get("url", ""),
                "source_published_at": _datetime(f"{published}T00:00:00+00:00") if published else None,
            })
        return items
