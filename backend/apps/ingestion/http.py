"""
Outbound HTTP for ingestion, in one place: a consistent User-Agent, hard
timeouts, a response-size cap, and — for URLs that come from *users*
(an opportunity's link) rather than admins (a feed URL) — an SSRF guard.

Why the guard matters: the worker fetches every submitted opportunity's
URL to pull its cover image. Without a check, anyone who can submit an
opportunity could point it at http://169.254.169.254/ or an internal
service and have our server request it. `fetch_public_html` refuses any
URL that resolves to a non-public address, and re-checks after every
redirect (redirects are followed manually for exactly that reason).
"""

import codecs
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

TIMEOUT = (5, 10)            # (connect, read) seconds
MAX_HTML_BYTES = 1_500_000   # the <head> we need is always near the top
MAX_REDIRECTS = 4


class NotFetchableError(ValueError):
    """Retrying won't help — e.g. the link is a PDF, not a web page."""


class UnsafeURLError(NotFetchableError):
    """The URL is not something the server should ever request."""


def user_agent() -> str:
    return getattr(settings, "INGESTION_USER_AGENT", "SimplyFindBot/1.0")


def default_headers(accept: str = "*/*") -> dict:
    return {"User-Agent": user_agent(), "Accept": accept}


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError(f"Only http(s) URLs are allowed: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURLError(f"{parsed.hostname} resolves to a non-public address")


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?\s*([A-Za-z0-9_\-]+)""", re.IGNORECASE)


def _charset(content_type: str, body: bytes) -> str:
    """Header charset, else the page's <meta charset>, else UTF-8.

    requests falls back to ISO-8859-1 for text/html without a charset
    header (an old HTTP/1.1 rule), which turns every em dash on a modern
    UTF-8 page into mojibake — so we don't use its guess."""
    match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
    if not match:
        match = _META_CHARSET.search(body[:4096])
        name = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    else:
        name = match.group(1)
    try:
        codecs.lookup(name)
        return name
    except LookupError:
        return "utf-8"


def fetch_public_html(url: str, session: requests.Session | None = None) -> tuple[str, str]:
    """GET a public web page and return (html_text, final_url).

    Raises NotFetchableError (incl. UnsafeURLError) when retrying can't
    help, and requests.RequestException for ordinary network problems
    (callers may retry those)."""
    session = session or requests.Session()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(current)
        response = session.get(
            current, headers=default_headers("text/html,application/xhtml+xml"),
            timeout=TIMEOUT, allow_redirects=False, stream=True,
        )
        try:
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise requests.RequestException("Redirect without a Location header")
                current = urljoin(current, location)
                continue

            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.lower():
                raise NotFetchableError(f"Not an HTML page ({content_type or 'unknown type'})")

            body = b""
            for chunk in response.iter_content(chunk_size=65536):
                body += chunk
                if len(body) >= MAX_HTML_BYTES:
                    break
            return body.decode(_charset(content_type, body), errors="replace"), current
        finally:
            response.close()

    raise requests.RequestException(f"Too many redirects for {url}")


MAX_JSON_BYTES = 200_000


def fetch_public_json(url: str, session: requests.Session | None = None) -> tuple[dict, str]:
    """GET a public JSON document (an Open Badge, say) with the same SSRF
    guard as fetch_public_html. Returns (data, final_url)."""
    import json

    session = session or requests.Session()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(current)
        response = session.get(
            current, headers=default_headers("application/ld+json, application/json"),
            timeout=TIMEOUT, allow_redirects=False, stream=True,
        )
        try:
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise requests.RequestException("Redirect without a Location header")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            body = b""
            for chunk in response.iter_content(chunk_size=65536):
                body += chunk
                if len(body) > MAX_JSON_BYTES:
                    raise NotFetchableError("The document is too large")
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except ValueError as exc:
                raise NotFetchableError("Not a JSON document") from exc
            if not isinstance(data, dict):
                raise NotFetchableError("Not a JSON object")
            return data, current
        finally:
            response.close()

    raise requests.RequestException(f"Too many redirects for {url}")
