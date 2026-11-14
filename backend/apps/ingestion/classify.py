"""
Small heuristics applied to every fetched item before it's stored:

  * classify_role — SimplyFind only lists roles for students and recent
    graduates. Each item is sorted into a role type (internship, graduate
    programme, entry-level, graduate school) from its own <category> tags,
    title and text, or dropped: senior roles, roles asking for more than
    settings.MAX_EXPERIENCE_YEARS of experience, and the scholarships,
    grants and competitions that aggregator feeds mix in.
  * guess_field — the field of work (an OpportunityCategory), from the
    same text; no match keeps the source's default.
  * find_deadline — those feeds put the closing date in the post body
    ("Deadline: October 27, 2026"). Without it every fetched listing
    looks open forever and never shows in "closing soon".
"""

import re
from dataclasses import dataclass
from datetime import datetime, time
from datetime import timezone as dt_timezone

from django.conf import settings

# Titles that mark a role as beyond entry level. "Management trainee" and
# "graduate assistant" are entry level, so they are checked first.
_ENTRY_TITLE = re.compile(
    r"(?i)\b(interns?|internships?|attachments?|industrial (training|placement)|placement year|"
    r"graduate (trainee|programme|program|scheme|associate|assistant)|management trainee|trainee|"
    r"apprentice(ship)?|entry[- ]level|junior|jr\.?|national service|nysc|fresh graduates?|recent graduates?|"
    r"early[- ]career|new grad)\b"
)
_SENIOR_TITLE = re.compile(
    r"(?i)\b(senior|sr\.?|lead|principal|staff|manager|director|head of|chief|vp|vice president|"
    r"president|partner|executive|expert|specialist ii+|consultant ii+|supervisor|coordinator ii+)\b"
)
_INTERNSHIP = re.compile(
    r"(?i)\b(interns?|internships?|attachments?|industrial (training|placement)|placement year|"
    r"national service|nysc)\b"
)
_GRAD_PROGRAMME = re.compile(
    r"(?i)\b(graduate (trainee|programme|program|scheme|associate)|management trainee|trainee|"
    r"apprentice(ship)?|new grad|fresh graduates?)\b"
)
_GRAD_SCHOOL = re.compile(
    r"(?i)\b(master'?s|masters|msc|m\.sc|mba|mphil|phd|ph\.d|doctoral|postgraduate|graduate school|"
    r"graduate study|graduate studies|graduate admissions?)\b"
)
# What aggregator feeds mix in that isn't a role (or a graduate school place).
_NOT_A_ROLE = re.compile(
    r"(?i)\b(scholarships?|bursar(y|ies)|fellowships?|grants?|funding|call for proposals|prizes?|awards?|"
    r"competitions?|contests?|challenges?|hackathons?|conferences?|summits?|webinars?|exchange programme)\b"
)
# "3+ years of experience", "minimum of 5 years' experience", "3-5 years experience"
_EXPERIENCE = re.compile(
    r"(?i)(?:at least|minimum(?: of)?|min\.?)?\s*(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*"
    r"years?(?:'|’)?\s+(?:of\s+)?(?:relevant\s+|professional\s+|work(?:ing)?\s+|post-qualification\s+)?"
    r"experience"
)


@dataclass
class RoleGuess:
    role_type: str
    experience_years: int


def required_experience(text: str) -> int | None:
    """The smallest 'N years of experience' the text asks for, or None."""
    found = [int(m.group(1)) for m in _EXPERIENCE.finditer(text or "")]
    return min(found) if found else None


def classify_role(item: dict, default_role_type: str = "") -> RoleGuess | None:
    """Which role type an item is, or None if it isn't for students and
    recent graduates. `default_role_type` is the source's own (blank for
    mixed feeds): a graduate-school source keeps its items as graduate
    school; a job source never turns them into graduate school places."""
    title = item.get("title") or ""
    tags = " ".join(item.get("categories") or [])
    body = f"{item.get('description') or ''} {item.get('sections_text') or ''}"
    experience = required_experience(f"{title} {body}")
    if experience is not None and experience > settings.MAX_EXPERIENCE_YEARS:
        return None

    if default_role_type == "graduate_school":
        if _GRAD_SCHOOL.search(f"{title} {tags}") or not _ENTRY_TITLE.search(title):
            return RoleGuess("graduate_school", 0)
        return None

    entry_title = _ENTRY_TITLE.search(title)
    if _SENIOR_TITLE.search(title) and not entry_title:
        return None
    heading = f"{title} {tags}"
    if _INTERNSHIP.search(heading):
        return RoleGuess("internship", experience or 0)
    if _GRAD_PROGRAMME.search(heading):
        return RoleGuess("graduate_programme", experience or 0)
    if _NOT_A_ROLE.search(heading):
        return None  # a scholarship, grant or contest in a mixed feed
    if entry_title or default_role_type in ("internship", "graduate_programme", "entry_level"):
        # Said to be entry level, or the source only lists such roles. A
        # plain job title with no experience asked for counts too, but only
        # when the source is marked entry level.
        if entry_title or experience is not None or default_role_type:
            return RoleGuess(default_role_type or "entry_level", experience or 0)
    return None


# Field of work, checked in order; no match keeps the source's default.
FIELD_KEYWORDS = [
    ("engineering-tech", ("software", "developer", "engineer", "data ", "it support", "ict", "cyber",
                          "computer", "technology", "tech ", "network", "devops", "qa ")),
    ("health", ("health", "medical", "nurse", "nursing", "clinical", "pharmac", "laborator", "hospital")),
    ("agriculture-environment", ("agri", "farm", "food security", "climate", "environment", "forestry",
                                 "water", "wash ")),
    ("ngo-development", ("humanitarian", "ngo", "development", "unicef", "undp", "unhcr", "wfp", "relief",
                         "protection", "programme assistant", "program assistant")),
    ("business-finance", ("finance", "account", "audit", "bank", "sales", "marketing", "business",
                          "operations", "procurement", "supply chain", "logistics", "consult", "hr ",
                          "human resources")),
    ("education", ("teach", "education", "research", "tutor", "academic", "school")),
    ("law-government", ("legal", "law", "policy", "government", "parliament", "public sector")),
    ("media-communications", ("media", "communication", "journalis", "design", "content", "social media",
                              "film", "photograph")),
]


def guess_field(item: dict, default, categories_by_slug: dict):
    """categories_by_slug: active OpportunityCategory rows keyed by slug."""
    text = f" {' '.join(item.get('categories') or [])} {item.get('title', '')} ".lower()
    for slug, keywords in FIELD_KEYWORDS:
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
