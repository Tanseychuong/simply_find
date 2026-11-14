from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ingestion.classify import classify_role, find_deadline, guess_field
from apps.ingestion.connectors.job_boards import (
    AshbyConnector,
    GreenhouseConnector,
    WorkableConnector,
    board_name,
)
from apps.ingestion.management.commands.setup_fetch_sources import SOURCES
from apps.ingestion.models import FetchLog, FetchSource
from apps.ingestion.services import fetch_source as run_fetch
from apps.opportunities.management.commands.setup_categories import DEFAULT_CATEGORIES
from apps.opportunities.models import Opportunity, OpportunityCategory

GREENHOUSE_JOBS = {"jobs": [
    {
        "title": "Backend Engineer", "company_name": "Moniepoint",
        "content": "&lt;p&gt;Build &lt;b&gt;payments&lt;/b&gt;.&lt;/p&gt;",
        "location": {"name": "Lagos, Nigeria"},
        "absolute_url": "https://job-boards.greenhouse.io/moniepoint/jobs/1",
        "first_published": "2026-10-01T08:00:00-04:00",
    },
    {
        "title": "Data Analyst", "content": "", "location": {"name": "Berlin, Germany"},
        "absolute_url": "https://job-boards.greenhouse.io/moniepoint/jobs/2",
    },
    {"title": "", "absolute_url": "https://job-boards.greenhouse.io/moniepoint/jobs/3"},
]}

ASHBY_JOBS = {"jobs": [
    {
        "title": "Program Associate", "descriptionPlain": "Support field teams.",
        "location": "Nairobi, Kenya", "secondaryLocations": [{"location": "Kampala, Uganda"}],
        "isRemote": False, "jobUrl": "https://jobs.ashbyhq.com/idinsight/1",
        "publishedAt": "2026-10-02T10:00:00.000+00:00",
    },
    {"title": "Hidden role", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/idinsight/2"},
    {"title": "Engineer", "location": "", "isRemote": True, "jobUrl": "https://jobs.ashbyhq.com/idinsight/3"},
]}

WORKABLE_JOBS = {"name": "Kuda Technologies", "jobs": [
    {
        "title": "Customer Support Officer", "shortlink": "https://apply.workable.com/j/ABC",
        "url": "https://apply.workable.com/kuda/j/ABC/",
        "locations": [{"city": "Lagos", "country": "Nigeria"}], "published_on": "2026-10-03",
        "telecommuting": False,
    },
    {"title": "Remote Engineer", "url": "https://apply.workable.com/kuda/j/DEF/",
     "city": "", "country": "", "telecommuting": True},
]}


def _json_response(payload):
    response = Mock()
    response.json = Mock(return_value=payload)
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def categories(db):
    return {
        slug: OpportunityCategory.objects.get_or_create(slug=slug, defaults={"name": slug.title()})[0]
        for slug, *_ in DEFAULT_CATEGORIES
    }


def _source(categories, connector, url, keywords=""):
    return FetchSource.objects.create(
        name="Test Board", connector_type=connector, url=url,
        category=categories["other"], include_keywords=keywords,
        role_type="entry_level",  # these tests are about fetching, not sorting roles
    )


class TestBoardName:
    @pytest.mark.parametrize("url, expected", [
        ("https://job-boards.greenhouse.io/moniepoint", "moniepoint"),
        ("https://job-boards.eu.greenhouse.io/jumia/jobs/123", "jumia"),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "acme"),
        ("https://jobs.ashbyhq.com/andela", "andela"),
        ("https://api.ashbyhq.com/posting-api/job-board/idinsight", "idinsight"),
        ("https://apply.workable.com/kuda/", "kuda"),
        ("https://apply.workable.com/api/v1/widget/accounts/fairmoney", "fairmoney"),
    ])
    def test_reads_board_from_page_and_api_urls(self, url, expected):
        assert board_name(url) == expected

    def test_bare_host_is_an_error(self):
        with pytest.raises(ValueError):
            board_name("https://jobs.ashbyhq.com/")


@pytest.mark.django_db
class TestJobBoardConnectors:
    @patch("apps.ingestion.connectors.job_boards.requests.get")
    def test_greenhouse(self, mock_get, categories):
        mock_get.return_value = _json_response(GREENHOUSE_JOBS)
        source = _source(categories, FetchSource.ConnectorType.GREENHOUSE, "https://job-boards.greenhouse.io/moniepoint")

        items = GreenhouseConnector(source).fetch()

        assert mock_get.call_args[0][0] == "https://boards-api.greenhouse.io/v1/boards/moniepoint/jobs?content=true"
        assert [i["title"] for i in items] == ["Backend Engineer", "Data Analyst"]  # untitled skipped
        first = items[0]
        assert first["description"] == "Build payments."  # double-escaped HTML fully stripped
        assert first["organization"] == "Moniepoint"
        assert first["location"] == "Lagos, Nigeria"
        assert first["source_published_at"].tzinfo is not None
        assert items[1]["organization"] == "Test Board"  # falls back to the source name

    @patch("apps.ingestion.connectors.job_boards.requests.get")
    def test_ashby(self, mock_get, categories):
        mock_get.return_value = _json_response(ASHBY_JOBS)
        source = _source(categories, FetchSource.ConnectorType.ASHBY, "https://jobs.ashbyhq.com/idinsight")

        items = AshbyConnector(source).fetch()

        assert mock_get.call_args[0][0] == "https://api.ashbyhq.com/posting-api/job-board/idinsight"
        assert [i["title"] for i in items] == ["Program Associate", "Engineer"]  # unlisted skipped
        assert items[0]["location"] == "Nairobi, Kenya, Kampala, Uganda"
        assert items[0]["description"] == "Support field teams."
        assert items[1]["location"].endswith("(Remote)")

    def test_region_locked_remote_roles_are_not_african(self):
        """Regression: Andela matched on "Remote" and pulled in 16 North America/UK-only roles."""
        andela = next(s for s in SOURCES if s[0] == "Andela")
        source = FetchSource(include_keywords=andela[5])
        assert not source.wants({"title": "Senior Engineer", "location": "North America (Remote)"})
        assert source.wants({"title": "Senior Engineer", "location": "Lagos, Nigeria (Remote)"})

    @patch("apps.ingestion.connectors.job_boards.requests.get")
    def test_workable(self, mock_get, categories):
        mock_get.return_value = _json_response(WORKABLE_JOBS)
        source = _source(categories, FetchSource.ConnectorType.WORKABLE, "https://apply.workable.com/kuda/")

        items = WorkableConnector(source).fetch()

        assert mock_get.call_args[0][0] == "https://apply.workable.com/api/v1/widget/accounts/kuda?details=true"
        assert items[0]["organization"] == "Kuda Technologies"
        assert items[0]["location"] == "Lagos, Nigeria"
        assert items[0]["opportunity_url"] == "https://apply.workable.com/j/ABC"
        assert items[0]["source_published_at"] == datetime(2026, 10, 3, tzinfo=dt_timezone.utc)
        assert items[1]["opportunity_url"] == "https://apply.workable.com/kuda/j/DEF/"
        assert items[1]["location"].endswith("(Remote)")

    @patch("apps.ingestion.connectors.job_boards.requests.get")
    def test_http_error_fails_the_fetch(self, mock_get, categories):
        response = _json_response({})
        response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = response
        source = _source(categories, FetchSource.ConnectorType.GREENHOUSE, "https://job-boards.greenhouse.io/gone")

        log = run_fetch(source)

        assert log.status == FetchLog.Status.FAILURE
        assert "404" in log.error_message
        assert not Opportunity.objects.exists()


@pytest.mark.django_db
class TestIncludeKeywords:
    @patch("apps.ingestion.connectors.job_boards.requests.get")
    def test_only_matching_locations_are_stored(self, mock_get, categories):
        mock_get.return_value = _json_response(GREENHOUSE_JOBS)
        source = _source(categories, FetchSource.ConnectorType.GREENHOUSE,
                         "https://job-boards.greenhouse.io/moniepoint", keywords="Nigeria, Kenya")

        log = run_fetch(source)

        assert log.items_found == 2
        assert log.items_created == 1
        stored = Opportunity.objects.get()
        assert stored.title == "Backend Engineer"
        assert stored.category == categories["engineering-tech"]  # field guessed from the title
        assert stored.status == Opportunity.Status.PENDING

    def test_matching_is_case_insensitive_and_ignores_description(self, categories):
        source = FetchSource(include_keywords=" ghana ,  REMOTE ,")
        assert source.keywords() == ["ghana", "remote"]
        assert source.wants({"title": "Engineer", "location": "Accra, GHANA"})
        assert source.wants({"title": "Remote Support", "location": ""})
        assert not source.wants({"title": "Engineer", "location": "Paris", "description": "Ghana office"})

    def test_blank_keeps_everything(self):
        assert FetchSource(include_keywords="").wants({"title": "Anything", "location": "Anywhere"})


class TestClassifyRole:
    @pytest.mark.parametrize("title, expected", [
        ("UN Graduate Internship Programme", "internship"),
        ("Software Engineering Intern (Summer 2027)", "internship"),
        ("Industrial attachment: Civil Engineering", "internship"),
        ("Graduate Trainee Programme 2027", "graduate_programme"),
        ("Management Trainee - Finance", "graduate_programme"),
        ("Junior Data Analyst", "entry_level"),
        ("Entry-level Accountant", "entry_level"),
    ])
    def test_student_roles_kept(self, title, expected):
        assert classify_role({"title": title}).role_type == expected

    @pytest.mark.parametrize("title", [
        "Senior Software Engineer",
        "Programme Manager, East Africa",
        "Director of Finance",
        "Head of Growth",
        "Mastercard Foundation Scholarship 2027",
        "Obama Foundation Leaders Fellowship",
        "Call for Proposals: Climate Innovation Grant",
        "Annual Report Published",
        "Accounts Officer",  # a plain job title from a mixed feed: not said to be entry level
    ])
    def test_everything_else_dropped(self, title):
        assert classify_role({"title": title}) is None

    def test_too_much_experience_drops_even_an_internship(self):
        item = {"title": "Research Intern", "description": "Requires at least 3 years of relevant experience."}
        assert classify_role(item) is None

    def test_experience_up_to_the_limit_is_kept_and_recorded(self):
        item = {"title": "Junior Analyst", "description": "1-2 years' experience preferred."}
        guess = classify_role(item)
        assert guess.role_type == "entry_level" and guess.experience_years == 1

    def test_entry_level_source_keeps_plain_titles_without_experience(self):
        assert classify_role({"title": "Accounts Officer"}, "entry_level").role_type == "entry_level"
        assert classify_role({"title": "Senior Accounts Officer"}, "entry_level") is None

    def test_graduate_school_source(self):
        assert classify_role({"title": "Fully funded Masters in Public Policy"}, "graduate_school").role_type \
            == "graduate_school"
        assert classify_role({"title": "Finance Intern"}, "graduate_school") is None

    def test_job_feed_never_makes_graduate_school_places(self):
        assert classify_role({"title": "Fully funded Masters in Public Policy"}) is None

    def test_feed_tags_count(self):
        assert classify_role({"title": "Join UNICEF", "categories": ["Internships"]}).role_type == "internship"


@pytest.mark.django_db
class TestGuessField:
    def test_title_decides_field(self, categories):
        assert guess_field({"title": "Software Engineering Intern"}, categories["other"], categories).slug \
            == "engineering-tech"
        assert guess_field({"title": "Nursing Graduate Trainee"}, categories["other"], categories).slug == "health"

    def test_no_match_keeps_default(self, categories):
        assert guess_field({"title": "Graduate Trainee"}, categories["other"], categories) == categories["other"]

    def test_inactive_field_is_never_chosen(self, categories):
        active = {k: v for k, v in categories.items() if k != "health"}
        assert guess_field({"title": "Nursing Intern"}, categories["other"], active).slug == "other"

    @patch("apps.ingestion.connectors.rss_connector.requests.get")
    def test_rss_items_are_sorted_and_filtered(self, mock_get, categories):
        feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
        <item><title>Software Engineering Internship 2027</title><link>https://ex.org/a</link>
          <description>Deadline: November 30, 2026</description></item>
        <item><title>XYZ Scholarship 2027</title><link>https://ex.org/b</link><description>Open now</description></item>
        <item><title>Senior Accountant</title><link>https://ex.org/c</link><description>Open now</description></item>
        </channel></rss>"""
        response = Mock(content=feed)
        response.raise_for_status = Mock()
        mock_get.return_value = response
        source = FetchSource.objects.create(name="Agg", connector_type=FetchSource.ConnectorType.RSS,
                                            url="https://ex.org/feed/", category=categories["other"])

        log = run_fetch(source)

        internship = Opportunity.objects.get(opportunity_url="https://ex.org/a")
        assert internship.category.slug == "engineering-tech" and internship.role_type == "internship"
        assert internship.application_deadline == datetime(2026, 11, 30, 23, 59, tzinfo=dt_timezone.utc)
        assert Opportunity.objects.count() == 1
        assert log.items_found == 3 and log.items_created == 1 and log.items_skipped == 2


class TestFindDeadline:
    @pytest.mark.parametrize("text, expected", [
        ("Deadline: October 27, 2026", (2026, 10, 27)),
        ("Application Deadline: 8 November 2026", (2026, 11, 8)),
        ("Closing date: 8th of November, 2026.", (2026, 11, 8)),
        ("Apply by December 2nd, 2026", (2026, 12, 2)),
        ("Deadline: Sept. 5, 2026", (2026, 9, 5)),
        ("Applications close on: Jan 15 2027", (2027, 1, 15)),
        ("The deadline for applications is March 3, 2027", (2027, 3, 3)),
    ])
    def test_formats(self, text, expected):
        found = find_deadline(f"Intro text. {text} More text.")
        assert (found.year, found.month, found.day) == expected
        assert (found.hour, found.minute) == (23, 59)

    @pytest.mark.parametrize("text", [
        "", "Published October 27, 2026", "Deadline: rolling", "Deadline: February 30, 2026", "Deadline: Foo 3, 2026",
    ])
    def test_no_deadline(self, text):
        assert find_deadline(text) is None


@pytest.mark.django_db
class TestSetupFetchSources:
    def test_creates_every_source_once(self, categories):
        call_command("setup_fetch_sources", stdout=Mock())
        assert FetchSource.objects.count() == len(SOURCES)

        source = FetchSource.objects.get(url="https://jobs.ashbyhq.com/andela")
        source.is_active = False
        source.save()
        call_command("setup_fetch_sources", stdout=Mock())

        assert FetchSource.objects.count() == len(SOURCES)
        assert not FetchSource.objects.get(url="https://jobs.ashbyhq.com/andela").is_active  # admin edit kept

    def test_dry_run_changes_nothing(self, categories):
        call_command("setup_fetch_sources", "--dry-run", stdout=Mock())
        assert not FetchSource.objects.exists()

    def test_every_source_has_a_working_connector_and_url(self):
        from apps.ingestion.connectors import get_connector_class
        from apps.opportunities.management.commands.setup_categories import (
            DEFAULT_CATEGORIES,
        )
        fields = {slug for slug, *_ in DEFAULT_CATEGORIES}
        for name, connector, url, slug, role_type, _keywords, interval, _active in SOURCES:
            assert get_connector_class(connector), name
            assert slug in fields, name
            assert role_type in {"", "internship", "graduate_programme", "entry_level", "graduate_school"}, name
            assert url.startswith("https://") and interval > 0, name
            if connector != FetchSource.ConnectorType.RSS:
                board_name(url)  # raises if the board URL is malformed
        assert len({url for _, _, url, *_ in SOURCES}) == len(SOURCES)  # no duplicates


@pytest.mark.django_db
class TestWorkerExitCode:
    def test_once_succeeds_when_cycle_completes(self):
        with patch("apps.ingestion.worker.run_cycle", return_value={"sources_fetched": 0}):
            call_command("run_ingestion_worker", "--once", stdout=Mock())

    def test_once_fails_when_cycle_crashes(self):
        """Regression: a crashed scheduled run used to exit 0 and show green in Actions."""
        with patch("apps.ingestion.worker.run_cycle", side_effect=RuntimeError("column does not exist")):
            with pytest.raises(CommandError):
                call_command("run_ingestion_worker", "--once", stdout=Mock())
