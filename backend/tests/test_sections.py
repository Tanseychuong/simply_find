"""
Descriptions in sections — About the organisation, Eligibility, Benefits,
How to apply …: reading them out of source HTML, storing them on fetch,
filling them during enrichment, and serving/accepting them over the API.
"""

import socket
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.ingestion.enrichment import enrich_opportunity
from apps.ingestion.models import FetchSource
from apps.ingestion.sections import classify, extract_sections
from apps.ingestion.services import fetch_source as run_fetch
from apps.opportunities.models import Opportunity
from apps.opportunities.sections import as_text, clean_sections, text_to_blocks

JOB_HTML = """
<h3>About One Acre Fund</h3><p>Founded in 2006, One Acre Fund supports smallholder farmers.</p>
<h3>About the Role</h3><p>This role leads the country programme.</p>
<h3>Responsibilities</h3><ul><li>Lead trials</li><li>Train staff</li></ul>
<h3>Qualifications</h3><ul><li>MSc in agronomy</li></ul>
<h3>Benefits</h3><p>Health insurance and housing.</p>
<h3>Application Deadline</h3><p>Deadline: November 30, 2026</p>
"""


def kinds(sections):
    return [s["kind"] for s in sections]


def section(sections, kind):
    return next(s for s in sections if s["kind"] == kind)


class TestExtractSections:
    def test_standard_headings_map_to_standard_sections_in_display_order(self):
        sections = extract_sections(JOB_HTML)

        assert kinds(sections) == [
            "overview", "organization", "eligibility", "responsibilities", "benefits", "dates",
        ]
        assert section(sections, "organization")["title"] == "About the organisation"
        assert section(sections, "responsibilities")["blocks"] == [
            {"type": "li", "text": "Lead trials"}, {"type": "li", "text": "Train staff"},
        ]

    def test_bold_paragraph_headings_and_inline_labels(self):
        html = """<p><strong>Deadline:</strong> November 17, 2026</p>
          <p>Applications are open for the Nexa Fund.</p>
          <p><strong>Eligibility</strong></p><ul><li>Aged 18-35</li></ul>
          <p><strong>Benefits</strong></p><p>Up to $2,000,000.</p>"""
        sections = extract_sections(html)

        # The label is one fact under its section; the intro after it stays the overview.
        assert section(sections, "dates")["blocks"] == [{"type": "p", "text": "Deadline: November 17, 2026"}]
        assert section(sections, "overview")["blocks"][0]["text"] == "Applications are open for the Nexa Fund."
        assert section(sections, "eligibility")["blocks"] == [{"type": "li", "text": "Aged 18-35"}]

    def test_numbered_sub_points_stay_in_their_section(self):
        html = """<h2>Scholarship Benefits</h2>
          <h3>1. Full Tuition Coverage</h3><p>All fees.</p>
          <h3>2. Stipend Start Date</h3><p>Paid monthly.</p>
          <h3>3. Health Allowance</h3><p>Up to $1,200.</p>
          <h2>Who Can Apply?</h2><h3>1. Education levels</h3><p>Undergraduates.</p>"""
        sections = extract_sections(html)

        benefits = section(sections, "benefits")["blocks"]
        assert [b["text"] for b in benefits if b["type"] == "h"] == [
            "1. Full Tuition Coverage", "2. Stipend Start Date", "3. Health Allowance",
        ]
        assert "dates" not in kinds(sections)  # "Start Date" was a sub-point, not a section
        assert section(sections, "eligibility")["blocks"][0] == {"type": "h", "text": "1. Education levels"}

    def test_spanish_and_french_headings(self):
        html = """<p><strong>Responsabilidades:</strong></p><ul><li>Mantener equipos</li></ul>
          <p><strong>Requisitos</strong></p><ul><li>Bachiller</li></ul>
          <h3>Comment postuler</h3><p>Envoyez votre CV.</p>"""
        assert kinds(extract_sections(html)) == ["eligibility", "responsibilities", "how_to_apply"]

    def test_site_chrome_is_dropped(self):
        html = """<h2>Eligibility</h2><p>Open to all.</p>
          <div class="sharedaddy"><h3>Share this:</h3><p>Facebook</p></div>
          <h2>Related Posts</h2><p>Another scholarship</p>
          <p>The post Foo appeared first on Bar.</p>
          <h2>How to Apply</h2><p><strong><a href="https://x.example">Click Here To Apply Online</a></strong></p>"""
        sections = extract_sections(html)
        assert as_text(sections) == "Open to all."

    def test_whole_page_reads_only_the_post_body(self):
        page = """<html><body><div class="site has-sidebar">
          <header><h1>Opportunity Desk</h1><nav><a href="/">Home</a></nav></header>
          <div class="entry-content">
            <p><strong>Eligibility</strong></p><ul><li>Applicants should be 18-35</li></ul>
            <h2>How to Apply</h2><p>Apply online.</p>
          </div>
          <aside class="sidebar"><h2>Benefits of subscribing</h2><p>Get alerts</p></aside>
          <article class="related"><h2>Benefits</h2><p>Some other post</p></article>
        </div></body></html>"""
        sections = extract_sections(page, page=True)
        assert kinds(sections) == ["eligibility", "how_to_apply"]
        assert "alerts" not in as_text(sections) and "other post" not in as_text(sections)

    def test_nothing_useful_returns_empty(self):
        assert extract_sections("<p>Just one paragraph about a programme.</p>") == []
        assert extract_sections("<html><body><p>No article here</p></body></html>", page=True) == []
        assert extract_sections("") == []

    @pytest.mark.parametrize("heading, kind", [
        ("About IDinsight", "organization"),
        ("About the Role", "overview"),
        ("About HENNGE Global Internship 2027", "overview"),
        ("Who Can Apply for the SMART Scholarship?", "eligibility"),
        ("Application Deadline", "dates"),
        ("Required Documents", "documents"),
        ("What you'll do", "responsibilities"),
        ("Nuts & Bolts", "other"),
    ])
    def test_classify(self, heading, kind):
        assert classify(heading) == kind


class TestCleanSections:
    def test_text_to_blocks(self):
        assert text_to_blocks("Open to students.\n- Aged 18-35\n• Based in Africa\n\n1. Has a degree") == [
            {"type": "p", "text": "Open to students."},
            {"type": "li", "text": "Aged 18-35"},
            {"type": "li", "text": "Based in Africa"},
            {"type": "li", "text": "Has a degree"},
        ]

    def test_drops_malformed_input_and_html_never_survives_as_markup(self):
        cleaned = clean_sections([
            "nonsense",
            {"kind": "eligibility", "blocks": [{"type": "script", "text": "x"}, {"type": "p", "text": " <b>Ok</b> "}]},
            {"kind": "made-up", "title": "Extra", "blocks": [{"type": "p", "text": "kept as other"}]},
            {"kind": "benefits", "blocks": [{"type": "h", "text": "only a heading"}]},
        ])
        assert cleaned == [
            {"kind": "eligibility", "title": "Eligibility", "blocks": [{"type": "p", "text": "<b>Ok</b>"}]},
            {"kind": "other", "title": "Extra", "blocks": [{"type": "p", "text": "kept as other"}]},
        ]  # stored as text; the frontend renders it as text, not HTML

    def test_a_long_section_cannot_crowd_out_the_rest(self):
        long_benefits = {"kind": "benefits", "blocks": [{"type": "p", "text": "x" * 1400}] * 30}
        eligibility = {"kind": "eligibility", "blocks": [{"type": "p", "text": "Open to all."}]}
        cleaned = clean_sections([long_benefits, eligibility])
        assert kinds(cleaned) == ["eligibility", "benefits"]


# --- Fetching ------------------------------------------------------------------

FEED = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item>
  <title>Warc Africa Aggregation Manager</title>
  <link>https://jobwebghana.com/jobs/aggregation-manager/</link>
  <description>Warc Africa is hiring. The post Aggregation Manager appeared first on JobWeb Ghana.</description>
  <content:encoded><![CDATA[
    <h2>About Warc</h2><p>Warc Africa supports farmers.</p>
    <h2>Requirements</h2><ul><li>Degree in Agriculture</li></ul>
    <h2>Application Information:</h2><p>Closing Date: October 30, 2026</p>
  ]]></content:encoded>
</item>
</channel></rss>"""


@pytest.fixture
def feed(db, category):
    return FetchSource.objects.create(
        name="JobWeb Ghana", connector_type=FetchSource.ConnectorType.RSS,
        url="https://jobwebghana.com/feed/", category=category,
    )


def _feed_response():
    response = Mock(content=FEED)
    response.raise_for_status = Mock()
    return response


@pytest.mark.django_db
class TestFetchStoresSections:
    def test_feed_article_becomes_sections_and_excerpt_the_summary(self, feed):
        with patch("apps.ingestion.connectors.rss_connector.requests.get", return_value=_feed_response()):
            run_fetch(feed)

        opportunity = Opportunity.objects.get()
        assert opportunity.description == "Warc Africa is hiring."  # WordPress footer stripped
        assert kinds(opportunity.sections) == ["organization", "eligibility", "how_to_apply"]
        # No deadline in the feed fields, but the sections had one.
        assert opportunity.application_deadline.date().isoformat() == "2026-10-30"

    def test_refetch_fills_sections_on_listings_fetched_before_them(self, feed):
        with patch("apps.ingestion.connectors.rss_connector.requests.get", return_value=_feed_response()):
            run_fetch(feed)
            Opportunity.objects.update(sections=[])  # as if fetched before this feature
            run_fetch(feed)

        assert Opportunity.objects.count() == 1
        assert kinds(Opportunity.objects.get().sections) == ["organization", "eligibility", "how_to_apply"]

    def test_refetch_never_overwrites_existing_sections(self, feed):
        mine = [{"kind": "benefits", "title": "Benefits", "blocks": [{"type": "p", "text": "Edited by a moderator"}]}]
        with patch("apps.ingestion.connectors.rss_connector.requests.get", return_value=_feed_response()):
            run_fetch(feed)
            Opportunity.objects.update(sections=mine)
            run_fetch(feed)
        assert Opportunity.objects.get().sections == mine


# --- Enrichment ---------------------------------------------------------------

ARTICLE = """<html><head><meta property="og:site_name" content="Opportunity Desk"></head><body>
<div class="entry-content">
  <p><strong>Deadline:</strong> December 1, 2026</p>
  <p>Applications are open for the Stanton Fellowship.</p>
  <p><strong>Eligibility</strong></p><ul><li>PhD holders</li></ul>
  <p><strong>Benefits</strong></p><p>A stipend of $80,000.</p>
  <p><a href="https://www.hertie-school.org/stanton">Click here to apply</a></p>
</div></body></html>"""

HOME = """<html><head><meta property="og:site_name" content="Hertie School">
<meta name="description" content="The Hertie School in Berlin prepares exceptional students for leadership
positions in government, business and civil society."></head><body></body></html>"""


def _public_dns():
    return patch("apps.ingestion.http.socket.getaddrinfo",
                 return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])


def _session(*pages):
    responses = []
    for html in pages:
        response = Mock(status_code=200, is_redirect=False, headers={"Content-Type": "text/html; charset=utf-8"})
        response.iter_content = Mock(return_value=[html.encode()])
        response.raise_for_status = Mock()
        responses.append(response)
    session = Mock()
    session.get = Mock(side_effect=responses)
    return session


@pytest.mark.django_db
class TestEnrichmentSections:
    LISTING = "https://opportunitydesk.org/2026/10/26/stanton/"

    def _fetched(self, category, **extra):
        return Opportunity.objects.create(
            category=category, title="Stanton Fellowship", description="Short.",
            opportunity_url=self.LISTING, listing_url=self.LISTING,
            source_type=Opportunity.SourceType.FETCHED, **extra,
        )

    def test_reads_sections_from_the_page_and_the_organisation_from_its_home_page(self, category):
        opportunity = self._fetched(category)
        session = _session(ARTICLE, HOME)
        with _public_dns():
            enrich_opportunity(opportunity, session=session)

        opportunity.refresh_from_db()
        assert kinds(opportunity.sections) == ["overview", "organization", "eligibility", "benefits", "dates"]
        assert section(opportunity.sections, "organization")["blocks"][0]["text"].startswith("The Hertie School")
        assert opportunity.organization == "Hertie School"
        assert opportunity.application_deadline.date().isoformat() == "2026-12-01"
        assert session.get.call_args_list[1].args[0] == "https://hertie-school.org/"  # the home page, not the call

    def test_already_resolved_listing_is_read_from_its_article(self, category):
        """Re-enriching a listing whose link already points at the organiser
        (an application form, often closed to bots) must read the
        aggregator's article — that's where the write-up is."""
        opportunity = self._fetched(category)
        Opportunity.objects.filter(pk=opportunity.pk).update(opportunity_url="https://forms.gle/abc")
        opportunity.refresh_from_db()
        session = _session(ARTICLE)
        with _public_dns():
            enrich_opportunity(opportunity, session=session)

        opportunity.refresh_from_db()
        assert session.get.call_args_list[0].args[0] == self.LISTING
        assert session.get.call_count == 1  # forms.gle is an application platform: no home-page visit
        assert opportunity.opportunity_url == "https://forms.gle/abc"
        assert "eligibility" in kinds(opportunity.sections)

    def test_existing_sections_are_kept(self, category):
        mine = [{"kind": "eligibility", "title": "Eligibility", "blocks": [{"type": "p", "text": "Set by hand"}]}]
        opportunity = self._fetched(category, sections=mine)
        with _public_dns():
            enrich_opportunity(opportunity, session=_session(ARTICLE, HOME))

        opportunity.refresh_from_db()
        assert section(opportunity.sections, "eligibility")["blocks"] == [{"type": "p", "text": "Set by hand"}]
        assert "organization" in kinds(opportunity.sections)  # a missing section is still added
        assert "benefits" not in kinds(opportunity.sections)

    def test_a_deadline_someone_set_is_kept(self, category):
        set_by_hand = timezone.now() + timedelta(days=60)
        opportunity = self._fetched(category, application_deadline=set_by_hand)
        with _public_dns():
            enrich_opportunity(opportunity, session=_session(ARTICLE, HOME))
        opportunity.refresh_from_db()
        assert opportunity.application_deadline == set_by_hand


# --- API --------------------------------------------------------------------------

@pytest.mark.django_db
class TestSectionsAPI:
    def test_detail_has_sections_and_list_does_not(self, api_client, admin_user, category):
        opportunity = Opportunity.objects.create(
            category=category, title="Fellowship", description="Short.",
            sections=extract_sections(JOB_HTML),
        )
        opportunity.approve(admin_user)
        past = timezone.now() - timedelta(days=3)  # out of the early-access window
        Opportunity.objects.filter(pk=opportunity.pk).update(published_at=past, free_access_at=past)

        detail = api_client.get(f"/api/opportunities/{opportunity.pk}/").data
        listing = api_client.get("/api/opportunities/").data["results"][0]

        assert kinds(detail["sections"])[:3] == ["overview", "organization", "eligibility"]
        assert "sections" not in listing

    def test_submission_with_sections(self, api_client, user, category):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/opportunities/", {
            "title": "Youth Grant", "description": "Grants for youth-led projects.", "category": category.id,
            "sections": [
                {"kind": "organization", "body": "We fund young leaders across Africa."},
                {"kind": "eligibility", "body": "- Aged 18-35\n- Leads a registered project"},
                {"kind": "benefits", "body": ""},
            ],
        }, format="json")

        assert response.status_code == 201, response.data
        stored = Opportunity.objects.get(title="Youth Grant").sections
        assert kinds(stored) == ["organization", "eligibility"]  # the empty one is dropped
        assert section(stored, "eligibility")["blocks"] == [
            {"type": "li", "text": "Aged 18-35"}, {"type": "li", "text": "Leads a registered project"},
        ]

    def test_submission_rejects_unknown_kinds(self, api_client, user, category):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/opportunities/", {
            "title": "X", "description": "Y", "category": category.id,
            "sections": [{"kind": "status", "body": "approved"}],
        }, format="json")
        assert response.status_code == 400

    def test_submission_without_sections_still_works(self, api_client, user, category):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/opportunities/", {
            "title": "Plain", "description": "desc", "category": category.id,
        })
        assert response.status_code == 201
        assert Opportunity.objects.get(title="Plain").sections == []
