"""
Small heuristics applied to every fetched item before it's stored:

  * guess_category — aggregator feeds (Opportunity Desk etc.) mix
    scholarships, fellowships, grants and jobs in one feed, so one
    category per source is wrong for most items. The item's own <category>
    tags are checked first, then its title; no match keeps the source's
    default category.
  * find_deadline — those feeds put the closing date in the post body
    ("Deadline: October 27, 2026"). Without it every fetched listing
    looks open forever and never shows in "closing soon".
"""

import re
from datetime import datetime, time
from datetime import timezone as dt_timezone

# Checked in this order: a "Masters scholarship for a fellowship year"
# is a scholarship, a "grant-funded internship" is a job, and so on.
CATEGORY_KEYWORDS = [
    ("scholarships", ("scholarship", "bursary", "masters", "master's", "phd", "postgraduate", "undergraduate study")),
    ("fellowships", ("fellowship", "fellows", "leadership program", "leadership programme", "accelerator", "residency")),
    ("jobs", ("internship", "intern ", "vacancy", "vacancies", "job", "career", "graduate trainee", "hiring", "recruitment")),
    ("grants", ("grant", "funding", "call for proposals", "prize", "award", "competition", "contest", "challenge")),
]


def guess_category(item: dict, default, categories_by_slug: dict):
    """categories_by_slug: active OpportunityCategory rows keyed by slug."""
    for text in [*item.get("categories", []), item.get("title", "")]:
        text = f" {text.lower()} "
        for slug, keywords in CATEGORY_KEYWORDS:
            if slug in categories_by_slug and any(k in text for k in keywords):
                return categories_by_slug[slug]
    return default


MONTHS = {
    m: i for i, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
         ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
         ("oct", "october"), ("nov", "november"), ("dec", "december")], start=1)
    for m in names
}
_MONTH = r"(?P<month>[A-Za-z]{3,9})\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>20\d\d)"
_DATE_PATTERNS = [
    re.compile(rf"{_MONTH},?\s+{_DAY},?\s+{_YEAR}"),     # October 27, 2026 / November, 12, 2026 / December 2nd, 2026
    re.compile(rf"{_DAY}\s+(?:of\s+)?{_MONTH},?\s+{_YEAR}"),  # 8 November 2026 / 8th of November, 2026
]
# Everything after the keyword is searched, so "Deadline: <date>" and
# "Apply by <date>" (no colon) both work.
_DEADLINE = re.compile(r"(?i)(?:deadline|closing date|apply by|applications close)([^\n]{0,90})")


def find_deadline(text: str):
    """The first 'Deadline: <date>' in text, as an aware datetime at the end
    of that day (UTC), or None."""
    for match in _DEADLINE.finditer(text or ""):
        window = match.group(1)
        for pattern in _DATE_PATTERNS:
            found = pattern.search(window)
            if not found:
                continue
            month = MONTHS.get(found.group("month").lower())
            if not month:
                continue
            try:
                day = datetime(int(found.group("year")), month, int(found.group("day"))).date()
            except ValueError:
                continue
            return datetime.combine(day, time(23, 59), tzinfo=dt_timezone.utc)
    return None
