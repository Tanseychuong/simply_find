"""
Fetched listings link to the organiser, not the aggregator that posted
them: finding the organiser link in an article, swapping it in during
enrichment, and what that means for de-duplication.
"""

import socket
from unittest.mock import Mock, patch

import pytest

from apps.ingestion.enrichment import enrich_opportunity
from apps.ingestion.models import FetchSource
from apps.ingestion.organizer import find_organizer_url, site_domain
from apps.ingestion.services import fetch_source as run_fetch
from apps.opportunities.models import Opportunity

LISTING = "https://opportunitydesk.org/2026/10/26/stanton-fellows/"
APPLY = "https://hertie-school.dvinci-easy.com/en/jobs/81081/stanton-fellow"

ARTICLE = f"""<!doctype html><html><head>
<meta property="og:site_name" content="Opportunity Desk">
<meta property="og:image" content="https://opportunitydesk.org/cover.jpg">
</head><body>
<header><nav><a href="https://partner.example/apply">Apply for our newsletter</a></nav></header>
<article>
  <p>The <a href="https://www.hertie-school.org/en/stanton">Stanton Fellows Program</a> funds research.</p>
  <a href="https://wa.me/?text=Stanton">Share on WhatsApp — apply</a>
  <a href="/about/">Apply for jobs at Opportunity Desk</a>
  <p><a href="{APPLY}">Click here to apply</a></p>
  <p><a href="https://www.hertie-school.org/en/stanton-official">Official Website</a></p>
</article>
<aside><a href="https://ads.example/apply-now">Apply now!</a></aside>
<footer><a href="https://akismet.com/privacy/">Learn how your comment data is processed.</a></footer>
</body></html>"""

ORGANIZER_PAGE = """<html><head><meta property="og:site_name" content="UNU-EHS"></head><body></body></html>"""


class TestFindOrganizerURL:
    def test_generic_link_text_is_judged_by_its_sentence(self):
        html = """<article><p>Candidates must apply through the online form.</p>
          <p>CLICK <a href="https://docs.google.com/forms/d/e/abc/viewform">HERE</a> TO APPLY</p>
          <p>Read more <a href="https://news.example/story">here</a>.</p></article>"""
        assert find_organizer_url(html, LISTING) == "https://docs.google.com/forms/d/e/abc/viewform"

    def test_french_posting(self):
        html = """<main><h2>How to apply</h2><p>Pour postuler, merci de nous faire parvenir votre CV
          <a href="https://alliance.alima.ngo/jobs/545">ici</a> avant le 09/11/2026.</p></main>"""
        assert find_organizer_url(html, "https://reliefweb.int/job/4235615/x") == "https://alliance.alima.ngo/jobs/545"

    def test_picks_the_apply_link_in_the_article(self):
        assert find_organizer_url(ARTICLE, LISTING) == APPLY

    def test_official_webpage_wording(self):
        html = """<div class="entry-content">
          <a href="https://www.vliruos.be/country-list">25 eligible countries</a>
          <a href="https://www.vliruos.be/calls/icp-2027">Visit the Official Webpage of the VLIR-UOS Scholarships</a>
        </div>"""
        assert find_organizer_url(html, "https://www.opportunitiesforafricans.com/vlir/") == \
            "https://www.vliruos.be/calls/icp-2027"

    def test_bare_url_link_like_reliefweb_how_to_apply(self):
        html = """<main><h2>How to apply</h2>
          <a href="https://apply.workable.com/mdm/j/36802C3CC5">https://apply.workable.com/mdm/j/36802C3CC5</a>
        </main><footer><a href="https://unocha.org/">OCHA website</a></footer>"""
        assert find_organizer_url(html, "https://reliefweb.int/job/4235617/coordinator") == \
            "https://apply.workable.com/mdm/j/36802C3CC5"

    def test_no_clear_link_returns_blank(self):
        html = """<article><a href="https://other.example/">Some programme</a>
          <a href="mailto:jobs@company.example">Apply by email</a></article>"""
        assert find_organizer_url(html, LISTING) == ""

    def test_links_to_the_feed_host_count_as_the_aggregator(self):
        html = '<article><a href="https://feeds.aggregator.example/x">Apply here</a></article>'
        assert find_organizer_url(html, "https://www.aggregator.com/post", ("https://aggregator.example/feed",)) == ""

    @pytest.mark.parametrize("host, expected", [
        ("www.opportunitydesk.org", "opportunitydesk.org"),
        ("jobs.example.com.gh", "example.com.gh"),
        ("https://sub.uni.ac.uk/page", "uni.ac.uk"),
    ])
    def test_site_domain(self, host, expected):
        assert site_domain(host) == expected


def _public_dns():
    return patch("apps.ingestion.http.socket.getaddrinfo",
                 return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])


def _session(*pages):
    """Each GET returns the next page, in order."""
    responses = []
    for html in pages:
        response = Mock(status_code=200, is_redirect=False, headers={"Content-Type": "text/html; charset=utf-8"})
        response.iter_content = Mock(return_value=[html.encode()])
        response.raise_for_status = Mock()
        responses.append(response)
    session = Mock()
    session.get = Mock(side_effect=responses)
    return session


@pytest.fixture
def feed(db, category):
    return FetchSource.objects.create(
        name="Opportunity Desk", connector_type=FetchSource.ConnectorType.RSS,
        url="https://opportunitydesk.org/feed/", category=category,
        role_type="entry_level",  # these tests are about fetching, not sorting roles
    )


@pytest.fixture
def fetched(feed, category):
    return Opportunity.objects.create(
        category=category, title="Stanton Fellows", description="Short.",
        opportunity_url=LISTING, listing_url=LISTING,
        source_type=Opportunity.SourceType.FETCHED, fetch_source=feed,
    )


@pytest.mark.django_db
class TestEnrichmentResolvesOrganizer:
    def test_swaps_in_organizer_link_and_keeps_the_listing(self, fetched):
        with _public_dns():
            enrich_opportunity(fetched, session=_session(ARTICLE))

        fetched.refresh_from_db()
        assert fetched.opportunity_url == APPLY
        assert fetched.listing_url == LISTING
        assert fetched.image_url == "https://opportunitydesk.org/cover.jpg"
        # dvinci is an application platform: its name isn't the organiser's,
        # and the aggregator's name never is either.
        assert fetched.organization == ""

    def test_organization_comes_from_the_organizer_site(self, fetched):
        article = ARTICLE.replace(APPLY, "https://unu.edu/ehs/msc-apply")
        with _public_dns():
            enrich_opportunity(fetched, session=_session(article, ORGANIZER_PAGE))

        fetched.refresh_from_db()
        assert fetched.opportunity_url == "https://unu.edu/ehs/msc-apply"
        assert fetched.organization == "UNU-EHS"

    def test_corrects_organization_copied_from_the_aggregator(self, fetched):
        fetched.organization = "Opportunity Desk"  # what the old enrichment stored
        fetched.save()
        with _public_dns():
            enrich_opportunity(fetched, session=_session(ARTICLE))

        fetched.refresh_from_db()
        assert fetched.organization == ""

    def test_a_moderator_edited_url_is_left_alone(self, fetched):
        fetched.opportunity_url = "https://hertie-school.org/fixed-by-hand"
        fetched.save()
        with _public_dns():
            enrich_opportunity(fetched, session=_session(ARTICLE, ORGANIZER_PAGE))

        fetched.refresh_from_db()
        assert fetched.opportunity_url == "https://hertie-school.org/fixed-by-hand"

    def test_no_organizer_link_keeps_the_listing_url(self, fetched):
        with _public_dns():
            enrich_opportunity(fetched, session=_session("<html><head></head><body><p>Email us.</p></body></html>"))

        fetched.refresh_from_db()
        assert fetched.opportunity_url == LISTING
        assert fetched.enrichment_status == Opportunity.EnrichmentStatus.DONE

    def test_submitted_listings_are_not_rewritten(self, user, category):
        submitted = Opportunity.objects.create(
            posted_by=user, category=category, title="Mine", description="Short.", opportunity_url=LISTING,
        )
        with _public_dns():
            enrich_opportunity(submitted, session=_session(ARTICLE))

        submitted.refresh_from_db()
        assert submitted.opportunity_url == LISTING
        assert submitted.organization == "Opportunity Desk"

    def test_same_call_from_a_second_aggregator_is_rejected_as_duplicate(self, fetched, category):
        with _public_dns():
            enrich_opportunity(fetched, session=_session(ARTICLE))
        other_listing = "https://opportunitiescorners.com/stanton-fellows/"
        copy = Opportunity.objects.create(
            category=category, title="Stanton Fellows 2027", description="Short.",
            opportunity_url=other_listing, listing_url=other_listing,
            source_type=Opportunity.SourceType.FETCHED,
        )
        with _public_dns():
            enrich_opportunity(copy, session=_session(ARTICLE.replace("opportunitydesk.org", "opportunitiescorners.com")))

        copy.refresh_from_db()
        fetched.refresh_from_db()
        assert copy.status == Opportunity.Status.REJECTED
        assert f"#{fetched.pk}" in copy.rejection_reason
        assert fetched.status == Opportunity.Status.PENDING

    def test_jobs_sharing_one_application_form_are_not_duplicates(self, fetched, feed, category):
        with _public_dns():
            enrich_opportunity(fetched, session=_session(ARTICLE))
        sibling_listing = "https://opportunitydesk.org/2026/10/26/head-of-legal/"
        sibling = Opportunity.objects.create(  # same source, different job, same form
            category=category, title="Head of Legal", description="Short.",
            opportunity_url=sibling_listing, listing_url=sibling_listing,
            source_type=Opportunity.SourceType.FETCHED, fetch_source=feed,
        )
        unrelated = Opportunity.objects.create(  # another source, different title, same form
            category=category, title="Procurement Officer", description="Short.",
            opportunity_url="https://jobs.example/p", listing_url="https://jobs.example/p",
            source_type=Opportunity.SourceType.FETCHED,
        )
        with _public_dns():
            enrich_opportunity(sibling, session=_session(ARTICLE))
            enrich_opportunity(unrelated, session=_session(ARTICLE.replace("opportunitydesk.org", "jobs.example")))

        sibling.refresh_from_db()
        unrelated.refresh_from_db()
        assert sibling.opportunity_url == unrelated.opportunity_url == APPLY
        assert sibling.status == unrelated.status == Opportunity.Status.PENDING


@pytest.mark.django_db
class TestFetchKeepsListing:
    FEED = f"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Stanton Fellows</title><link>{LISTING}</link></item>
    </channel></rss>""".encode()

    def _get(self):
        response = Mock(content=self.FEED)
        response.raise_for_status = Mock()
        return response

    def test_rss_items_record_the_listing(self, feed):
        with patch("apps.ingestion.connectors.rss_connector.requests.get", return_value=self._get()):
            run_fetch(feed)
        assert Opportunity.objects.get().listing_url == LISTING

    def test_refetch_after_swap_does_not_duplicate(self, feed):
        with patch("apps.ingestion.connectors.rss_connector.requests.get", return_value=self._get()):
            run_fetch(feed)
            Opportunity.objects.update(opportunity_url=APPLY)  # enrichment found the organiser
            run_fetch(feed)
        assert Opportunity.objects.count() == 1
