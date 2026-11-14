"""
The automatic half of ingestion: the scheduler picks up only what's due,
the worker command runs a cycle, and every opportunity gets enriched with
its page's image/summary — safely.
"""

import socket
from io import StringIO
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.ingestion.enrichment import MAX_ATTEMPTS, enrich_opportunity, extract_metadata
from apps.ingestion.http import NotFetchableError, UnsafeURLError, assert_public_url
from apps.ingestion.models import FetchSource
from apps.ingestion.scheduler import claim_due_sources, run_due_sources, run_pending_enrichment
from apps.opportunities.models import Opportunity

PAGE = """<!doctype html><html><head>
<title>Fallback title</title>
<meta property="og:site_name" content="Global Youth Fund">
<meta property="og:description" content="A fully funded fellowship for emerging leaders &amp; organisers.">
<meta property="og:image" content="/images/cover.jpg">
</head><body><meta property="og:image" content="https://evil.example/ignored.jpg"></body></html>"""


def _public_dns(ip="93.184.216.34"):
    return patch("apps.ingestion.http.socket.getaddrinfo",
                 return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])


def _html_session(html=PAGE, status=200, content_type="text/html; charset=utf-8", headers=None, encoding="utf-8"):
    response = Mock(status_code=status, is_redirect=False, encoding=encoding,
                    headers={"Content-Type": content_type, **(headers or {})})
    response.iter_content = Mock(return_value=[html.encode()])
    response.raise_for_status = Mock()
    session = Mock()
    session.get = Mock(return_value=response)
    return session


@pytest.fixture
def source(db, category):
    return FetchSource.objects.create(
        name="Feed", connector_type=FetchSource.ConnectorType.RSS,
        url="https://example.com/feed.xml", category=category,
    )


@pytest.fixture
def opportunity(db, user, category):
    return Opportunity.objects.create(
        posted_by=user, category=category, title="Fellowship", description="Short.",
        opportunity_url="https://example.com/fellowship",
    )


# --- Scheduler -------------------------------------------------------------

@pytest.mark.django_db
class TestScheduler:
    def test_only_due_active_sources_are_claimed(self, source, category):
        now = timezone.now()
        FetchSource.objects.create(name="Later", connector_type="rss", url="https://a.example/f",
                                   category=category, next_fetch_at=now + timedelta(hours=1))
        FetchSource.objects.create(name="Off", connector_type="rss", url="https://b.example/f",
                                   category=category, is_active=False)

        claimed = claim_due_sources(limit=10, now=now)

        assert [s.name for s in claimed] == ["Feed"]

    def test_claiming_pushes_source_forward_so_it_is_not_claimed_twice(self, source):
        now = timezone.now()
        assert claim_due_sources(limit=10, now=now)
        assert claim_due_sources(limit=10, now=now) == []

    @patch("apps.ingestion.scheduler.fetch_source")
    def test_run_due_sources_fetches_each_due_source(self, mock_fetch, source):
        mock_fetch.return_value = Mock(items_created=2, items_found=2, status="success")

        logs = run_due_sources(limit=10)

        mock_fetch.assert_called_once()
        assert len(logs) == 1

    @patch("apps.ingestion.scheduler.enrich_opportunity")
    def test_enrichment_claims_pending_items_once(self, mock_enrich, opportunity):
        assert run_pending_enrichment(limit=10) == 1
        assert run_pending_enrichment(limit=10) == 0  # leased, not retried immediately
        mock_enrich.assert_called_once()

    @patch("apps.ingestion.worker.run_cycle", return_value={"sources_fetched": 0})
    def test_worker_command_runs_one_cycle(self, mock_cycle):
        call_command("run_ingestion_worker", "--once", stdout=StringIO())
        mock_cycle.assert_called_once()

    @patch("apps.ingestion.worker.run_cycle", side_effect=RuntimeError("column does not exist"))
    def test_worker_command_once_fails_when_cycle_crashes(self, mock_cycle):
        # Regression: a crashed cycle exited 0, so the scheduled GitHub
        # Action showed green while ingestion was broken.
        with pytest.raises(CommandError, match="Ingestion cycle failed"):
            call_command("run_ingestion_worker", "--once", stdout=StringIO())


# --- SSRF guard --------------------------------------------------------------

class TestPublicURLGuard:
    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"])
    def test_rejects_private_addresses(self, ip):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        with patch("apps.ingestion.http.socket.getaddrinfo",
                   return_value=[(family, socket.SOCK_STREAM, 6, "", (ip, 80))]):
            with pytest.raises(UnsafeURLError):
                assert_public_url("http://internal.example/")

    @pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "http:///nohost"])
    def test_rejects_non_http_urls(self, url):
        with pytest.raises(UnsafeURLError):
            assert_public_url(url)

    def test_accepts_public_address(self):
        with _public_dns():
            assert_public_url("https://example.com/page")  # no exception


# --- Enrichment ----------------------------------------------------------------

class TestExtractMetadata:
    def test_reads_open_graph_tags_from_head_only(self):
        meta = extract_metadata(PAGE, "https://example.com/fellowship")

        assert meta["image_url"] == "https://example.com/images/cover.jpg"  # relative resolved
        assert meta["site_name"] == "Global Youth Fund"
        assert meta["description"] == "A fully funded fellowship for emerging leaders & organisers."

    def test_falls_back_to_title_tag(self):
        meta = extract_metadata("<html><head><title> Plain  page </title></head></html>", "https://x.example/")
        assert meta["title"] == "Plain page"
        assert meta["image_url"] == ""


@pytest.mark.django_db
class TestEnrichOpportunity:
    def test_fills_blanks_only(self, opportunity):
        opportunity.organization = "Set by a person"
        opportunity.save()

        with _public_dns():
            status = enrich_opportunity(opportunity, session=_html_session())

        opportunity.refresh_from_db()
        assert status == Opportunity.EnrichmentStatus.DONE
        assert opportunity.image_url == "https://example.com/images/cover.jpg"
        assert opportunity.description.startswith("A fully funded fellowship")  # "Short." was too short
        assert opportunity.organization == "Set by a person"                     # never overwritten

    def test_keeps_existing_image_and_long_description(self, opportunity):
        opportunity.image_url = "https://cdn.example/mine.jpg"
        opportunity.description = "A long, careful description written by the person who posted this listing."
        opportunity.save()

        with _public_dns():
            enrich_opportunity(opportunity, session=_html_session())

        opportunity.refresh_from_db()
        assert opportunity.image_url == "https://cdn.example/mine.jpg"
        assert opportunity.description.startswith("A long, careful description")

    def test_does_not_clobber_a_concurrent_approval(self, opportunity, admin_user):
        stale_copy = Opportunity.objects.get(pk=opportunity.pk)
        opportunity.approve(admin_user)  # happens while the worker holds an old copy

        with _public_dns():
            enrich_opportunity(stale_copy, session=_html_session())

        opportunity.refresh_from_db()
        assert opportunity.status == Opportunity.Status.APPROVED

    def test_unsafe_url_is_skipped_without_fetching(self, opportunity):
        session = _html_session()
        with patch("apps.ingestion.http.socket.getaddrinfo",
                   return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))]):
            status = enrich_opportunity(opportunity, session=session)

        assert status == Opportunity.EnrichmentStatus.SKIPPED
        session.get.assert_not_called()

    def test_redirect_to_private_address_is_blocked(self, opportunity):
        redirect = Mock(status_code=302, is_redirect=True, headers={"Location": "http://169.254.169.254/latest"})
        session = Mock()
        session.get = Mock(return_value=redirect)

        def resolve(host, *args, **kwargs):
            ip = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

        with patch("apps.ingestion.http.socket.getaddrinfo", side_effect=resolve):
            status = enrich_opportunity(opportunity, session=session)

        assert status == Opportunity.EnrichmentStatus.SKIPPED
        assert session.get.call_count == 1  # never followed into the metadata service

    def test_utf8_page_without_charset_header_is_not_mojibake(self, opportunity):
        page = PAGE.replace("emerging leaders &amp; organisers", "emerging leaders \u2014 organisers").replace(
            "<head>", '<head><meta charset="utf-8">')
        with _public_dns():
            enrich_opportunity(opportunity, session=_html_session(html=page, content_type="text/html", encoding="ISO-8859-1"))  # what requests guesses

        opportunity.refresh_from_db()
        assert "\u2014" in opportunity.description

    def test_non_html_link_is_skipped(self, opportunity):
        with _public_dns():
            status = enrich_opportunity(opportunity, session=_html_session(content_type="application/pdf"))
        assert status == Opportunity.EnrichmentStatus.SKIPPED

    def test_network_errors_retry_then_give_up(self, opportunity):
        session = Mock()
        session.get = Mock(side_effect=requests.ConnectionError("timeout"))

        with _public_dns():
            for _ in range(MAX_ATTEMPTS - 1):
                assert enrich_opportunity(opportunity, session=session) == Opportunity.EnrichmentStatus.PENDING
            assert enrich_opportunity(opportunity, session=session) == Opportunity.EnrichmentStatus.FAILED

        opportunity.refresh_from_db()
        assert opportunity.enrichment_attempts == MAX_ATTEMPTS

    def test_no_url_is_skipped(self, opportunity):
        opportunity.opportunity_url = ""
        assert enrich_opportunity(opportunity) == Opportunity.EnrichmentStatus.SKIPPED

    def test_not_fetchable_error_is_a_value_error(self):
        assert issubclass(NotFetchableError, ValueError)
