"""
How far we can check an online-learning credential.

Coursera, edX, Credly and LinkedIn Learning publish certificates on their
own sites. We check that the link really points at those certificate pages
("recognised_link"), which stops typos and look-alike domains, but a page
there doesn't prove it belongs to this person, and we say so.

An Open Badge (2.0, hosted verification) can be checked properly: we fetch
the issuer's assertion through the SSRF-guarded client, and it's
"verified" when it is an Assertion hosted where it says it is, its
recipient is this person's email (hashed or plain), and it isn't revoked
or expired.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse

import requests
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.ingestion.http import NotFetchableError, fetch_public_json

from .models import Credential

logger = logging.getLogger(__name__)

# provider -> ((host suffix, path prefixes), ...)
CERTIFICATE_PAGES = {
    Credential.Provider.COURSERA: (("coursera.org", ("/verify/", "/account/accomplishments/", "/share/")),),
    Credential.Provider.EDX: (("courses.edx.org", ("/certificates/",)), ("credentials.edx.org", ("/credentials/",))),
    Credential.Provider.CREDLY: (("credly.com", ("/badges/", "/earner/earned/badge/")),),
    Credential.Provider.LINKEDIN_LEARNING: (("linkedin.com", ("/learning/certificates/",)),),
}


@dataclass
class CheckResult:
    status: str
    detail: str = ""
    title: str = ""
    issuer: str = ""
    issued_on: object = None


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def provider_for_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for provider, pages in CERTIFICATE_PAGES.items():
        if any(_host_matches(host, suffix) for suffix, _ in pages):
            return provider
    return None


def is_certificate_page(provider: str, url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    return any(
        _host_matches(host, suffix) and path.startswith(prefixes)
        for suffix, prefixes in CERTIFICATE_PAGES.get(provider, ())
    )


def _recipient_matches(recipient: dict, email: str) -> bool:
    if not isinstance(recipient, dict) or recipient.get("type", "email") != "email":
        return False
    identity = str(recipient.get("identity", ""))
    email = email.strip().lower()
    if not recipient.get("hashed"):
        return identity.strip().lower() == email
    algorithm, _, digest = identity.partition("$")
    if algorithm.lower() not in ("sha256", "sha512") or not digest:
        return False
    salted = (email + str(recipient.get("salt") or "")).encode()
    expected = hashlib.new(algorithm.lower(), salted).hexdigest()
    return expected.lower() == digest.lower()


def _when(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _same_document(a: str, b: str) -> bool:
    return a.rstrip("/").split("#")[0] == b.rstrip("/").split("#")[0]


def _named(obj, session) -> tuple[dict, str]:
    """A badge or issuer may be embedded or given as a URL."""
    if isinstance(obj, str):
        data, _ = fetch_public_json(obj, session)
        return data, str(data.get("name", ""))
    if isinstance(obj, dict):
        return obj, str(obj.get("name", ""))
    return {}, ""


def verify_open_badge(url: str, email: str, session=None) -> CheckResult:
    session = session or requests.Session()
    try:
        assertion, final_url = fetch_public_json(url, session)
    except (NotFetchableError, requests.RequestException) as exc:
        logger.info("Open Badge fetch failed for %s: %s", url, exc)
        return CheckResult(Credential.Check.FAILED, "We couldn't read the badge from its issuer.")

    kind = assertion.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    if "Assertion" not in kinds:
        return CheckResult(Credential.Check.FAILED, "This link isn't an Open Badge assertion.")
    verification = assertion.get("verification") or {}
    if isinstance(verification, dict) and verification.get("type", "hosted").lower() not in ("hosted", "hostedbadge"):
        return CheckResult(Credential.Check.FAILED, "Only badges hosted by their issuer can be checked.")
    if not _same_document(str(assertion.get("id", "")), final_url) and not _same_document(str(assertion.get("id", "")), url):
        return CheckResult(Credential.Check.FAILED, "The badge isn't hosted where it says it is.")
    if not _recipient_matches(assertion.get("recipient"), email):
        return CheckResult(Credential.Check.FAILED, "The badge was issued to a different email address.")
    if assertion.get("revoked"):
        return CheckResult(Credential.Check.FAILED, "The issuer has revoked this badge.")
    expires = _when(assertion.get("expires"))
    if expires and expires < timezone.now():
        return CheckResult(Credential.Check.FAILED, "This badge has expired.")

    title = issuer = ""
    try:
        badge, title = _named(assertion.get("badge"), session)
        _, issuer = _named(badge.get("issuer"), session)
    except (NotFetchableError, requests.RequestException):
        pass  # the assertion itself checked out; names are only labels
    issued = _when(assertion.get("issuedOn"))
    return CheckResult(
        Credential.Check.VERIFIED, "Checked with the issuer.",
        title=title[:200], issuer=issuer[:200], issued_on=issued.date() if issued else None,
    )


def check_credential(credential: Credential, session=None) -> Credential:
    """Run the check that fits the provider and save the result."""
    email = credential.owner.email
    if credential.provider == Credential.Provider.OPEN_BADGE:
        result = verify_open_badge(credential.url, email, session)
    elif credential.provider in CERTIFICATE_PAGES:
        if is_certificate_page(credential.provider, credential.url):
            result = CheckResult(
                Credential.Check.RECOGNISED_LINK,
                f"The link opens a certificate page on {credential.get_provider_display()}. "
                "Open it to confirm the name on it.",
            )
        else:
            result = CheckResult(
                Credential.Check.FAILED,
                f"This isn't a {credential.get_provider_display()} certificate link.",
            )
    else:
        result = CheckResult(Credential.Check.UNCHECKED, "Links from other sites aren't checked.")

    credential.check_status = result.status
    credential.check_detail = result.detail
    credential.checked_at = timezone.now()
    if result.status == Credential.Check.VERIFIED:
        credential.title = credential.title or result.title or "Open Badge"
        credential.issuer = credential.issuer or result.issuer
        credential.issued_on = credential.issued_on or result.issued_on
    credential.save()
    return credential
