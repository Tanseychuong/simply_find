from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.ingestion.connectors.rss_connector import RSSConnector, clean_text
from apps.ingestion.models import FetchLog, FetchSource
from apps.ingestion.services import fetch_source as run_fetch
from apps.opportunities.models import Opportunity

SAMPLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item>
  <title>Sample Graduate Trainee</title>
  <link>https://example.com/fellowship</link>
  <description>&lt;p&gt;A &lt;b&gt;great&lt;/b&gt; opportunity.&lt;/p&gt;</description>
  <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
  <media:content url="https://example.com/cover.jpg" medium="image" />
</item>
</channel></rss>"""

SAMPLE_ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Grants</title>
  <entry>
    <title>Community Grant 2026</title>
    <link rel="alternate" href="https://example.org/grant"/>
    <summary type="html">&lt;p&gt;Up to $5,000 for local projects.&lt;/p&gt;</summary>
    <published>2026-02-01T09:30:00Z</published>
    <author><name>Example Foundation</name></author>
  </entry>
</feed>"""


@pytest.fixture
def rss_source(db, category):
    return FetchSource.objects.create(
        name="Test Feed", connector_type=FetchSource.ConnectorType.RSS,
        url="https://example.com/feed.xml", category=category,
        role_type="entry_level",  # these tests are about fetching, not sorting roles
    )


def _mock_response(content=SAMPLE_RSS):
    response = Mock(content=content)
    response.raise_for_status = Mock()
    return response


class TestRSSConnector:
    """Pure parsing logic — HTTP mocked out."""

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_parses_items(self, mock_get, rss_source):
        mock_get.return_value = _mock_response()

        items = RSSConnector(rss_source).fetch()

        assert len(items) == 1
        item = items[0]
        assert item["title"] == "Sample Graduate Trainee"
        assert item["opportunity_url"] == "https://example.com/fellowship"
        assert item["image_url"] == "https://example.com/cover.jpg"
        assert item["description"] == "A great opportunity."  # HTML stripped
        assert item["organization"] == ""  # not the feed's name — enrichment fills it from the organiser

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_web_page_instead_of_feed_says_so(self, mock_get, rss_source):
        mock_get.return_value = _mock_response(b"<!DOCTYPE html><html><body>Careers</body></html>")
        with pytest.raises(ValueError, match="web page, not an RSS/Atom feed"):
            RSSConnector(rss_source).fetch()

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_pubdate_is_publish_date_not_deadline(self, mock_get, rss_source):
        """Regression: pubDate used to be stored as the application deadline,
        which made every fetched listing look expired on arrival."""
        mock_get.return_value = _mock_response()

        item = RSSConnector(rss_source).fetch()[0]

        assert item["source_published_at"].year == 2026
        assert item.get("application_deadline") is None

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_parses_atom_feeds(self, mock_get, rss_source):
        mock_get.return_value = _mock_response(SAMPLE_ATOM)

        items = RSSConnector(rss_source).fetch()

        assert len(items) == 1
        assert items[0]["title"] == "Community Grant 2026"
        assert items[0]["opportunity_url"] == "https://example.org/grant"
        assert items[0]["organization"] == ""  # <author> wrote the post; it isn't the organiser
        assert items[0]["description"] == "Up to $5,000 for local projects."
        assert items[0]["source_published_at"].tzinfo is not None

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_skips_items_without_title(self, mock_get, rss_source):
        no_title_rss = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item><link>https://example.com/x</link></item></channel></rss>"""
        mock_get.return_value = _mock_response(no_title_rss)

        items = RSSConnector(rss_source).fetch()

        assert items == []

    def test_clean_text(self):
        assert clean_text("<p>Hello&nbsp;<em>world</em></p>\n\n  again") == "Hello world again"


@pytest.mark.django_db
class TestFetchSourceService:
    """The end-to-end behavior: a fetch creates PENDING opportunities and
    never auto-approves anything."""

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_creates_pending_opportunity(self, mock_get, rss_source):
        mock_get.return_value = _mock_response()

        log = run_fetch(rss_source)

        assert log.status == FetchLog.Status.SUCCESS
        assert log.items_created == 1
        opportunity = Opportunity.objects.get(title="Sample Graduate Trainee")
        assert opportunity.status == Opportunity.Status.PENDING
        assert opportunity.source_type == Opportunity.SourceType.FETCHED
        assert opportunity.fetch_source == rss_source
        assert opportunity.image_url == "https://example.com/cover.jpg"
        assert opportunity.application_deadline is None
        assert opportunity.enrichment_status == Opportunity.EnrichmentStatus.PENDING

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_does_not_duplicate_on_rerun(self, mock_get, rss_source):
        mock_get.return_value = _mock_response()

        run_fetch(rss_source)
        second_log = run_fetch(rss_source)

        assert Opportunity.objects.filter(title="Sample Graduate Trainee").count() == 1
        assert second_log.items_created == 0
        assert second_log.status == FetchLog.Status.PARTIAL

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_duplicates_inside_one_feed_are_created_once(self, mock_get, rss_source):
        twice = SAMPLE_RSS.replace(b"</channel>", SAMPLE_RSS.split(b"<channel>")[1].split(b"</channel>")[0] + b"</channel>")
        mock_get.return_value = _mock_response(twice)

        log = run_fetch(rss_source)

        assert log.items_found == 2
        assert log.items_created == 1

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_overlong_fields_are_clipped_not_fatal(self, mock_get, rss_source):
        long_title = b"T" * 450
        mock_get.return_value = _mock_response(SAMPLE_RSS.replace(b"Sample Graduate Trainee", long_title))

        log = run_fetch(rss_source)

        assert log.status == FetchLog.Status.SUCCESS
        assert len(Opportunity.objects.get().title) == 200

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_failure_is_logged_not_raised(self, mock_get, rss_source):
        mock_get.side_effect = Exception("network error")

        log = run_fetch(rss_source)  # should not raise

        assert log.status == FetchLog.Status.FAILURE
        assert "network error" in log.error_message

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_updates_last_fetched_at(self, mock_get, rss_source):
        mock_get.return_value = _mock_response()
        assert rss_source.last_fetched_at is None

        run_fetch(rss_source)
        rss_source.refresh_from_db()

        assert rss_source.last_fetched_at is not None

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_success_schedules_next_run_one_interval_later(self, mock_get, rss_source):
        mock_get.return_value = _mock_response()

        run_fetch(rss_source)
        rss_source.refresh_from_db()

        expected = rss_source.last_fetched_at + timedelta(minutes=rss_source.fetch_interval_minutes)
        assert abs((rss_source.next_fetch_at - expected).total_seconds()) < 5
        assert rss_source.consecutive_failures == 0

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_failures_back_off(self, mock_get, rss_source):
        mock_get.side_effect = Exception("down")

        run_fetch(rss_source)
        rss_source.refresh_from_db()
        first_gap = rss_source.next_fetch_at - rss_source.last_fetched_at

        run_fetch(rss_source)
        rss_source.refresh_from_db()
        second_gap = rss_source.next_fetch_at - rss_source.last_fetched_at

        assert rss_source.consecutive_failures == 2
        assert rss_source.last_error == "down"
        assert second_gap > first_gap
        assert second_gap <= timedelta(hours=24)


class TestSchedule:
    def test_schedule_backoff_is_capped(self):
        source = FetchSource(fetch_interval_minutes=60, consecutive_failures=20)
        now = timezone.now()
        source.schedule_next(succeeded=False, error="x", now=now)
        assert source.next_fetch_at - now == timedelta(hours=24)
