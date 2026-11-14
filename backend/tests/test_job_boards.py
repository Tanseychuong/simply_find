from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command

from apps.ingestion.classify import find_deadline
from apps.ingestion.connectors.job_boards import (
    AshbyConnector, GreenhouseConnector, WorkableConnector, board_name,
)
from apps.ingestion.models import FetchSource
from apps.ingestion.services import fetch_source as run_fetch
from apps.opportunities.models import Opportunity

GREENHOUSE = {"jobs": [
    {
        "title": "Field Officer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
        "location": {"name": "Accra, Ghana"}, "company_name": "Acme",
        "content": "&lt;p&gt;Work &amp;amp; grow.&lt;/p&gt;",
        "first_published": "2026-10-01T09:00:00-04:00", "application_deadline": "2026-11-30T00:00:00Z",
    },
    {"title": "Engineer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2", "location": {"name": "Austin, Texas"}},
]}
ASHBY = {"jobs": [
    {"title": "Analyst", "jobUrl": "https://jobs.ashbyhq.com/acme/a", "location": "Nairobi, Kenya",
     "secondaryLocations": [{"location": "Kigali, Rwanda"}], "isRemote": False, "isListed": True,
     "descriptionPlain": "Analyse things.", "publishedAt": "2026-10-02T10:00:00.000+00:00"},
    {"title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/acme/b", "location": "Lagos", "isListed": False},
]}
WORKABLE = {"name": "Acme Ltd", "jobs": [
    {"title": "Credit Analyst", "shortlink": "https://apply.workable.com/j/ABC", "published_on": "2026-10-03",
     "telecommuting": False, "locations": [{"city": "Lagos", "country": "Nigeria"}],
     "description": "<p>Acme lends to small firms.</p><p><strong>Requirements</strong></p>"
                    "<ul><li>2 years in credit</li></ul><p><strong>Benefits</strong></p><p>Health cover.</p>"},
]}


def _json_response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def board(db, category):
    def make(connector_type, url, keywords=""):
        return FetchSource.objects.create(
            name="Acme", connector_type=connector_type, url=url, category=category, include_keywords=keywords,
            role_type="entry_level",  # these tests are about fetching, not sorting roles
        )
    return make


class TestBoardName:
    @pytest.mark.parametrize("url", [
        "https://job-boards.greenhouse.io/acme", "https://boards.greenhouse.io/acme/jobs/123",
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs", "https://jobs.ashbyhq.com/acme",
        "https://apply.workable.com/acme/", "https://apply.workable.com/api/v1/widget/accounts/acme",
    ])
    def test_reads_board_from_any_url_form(self, url):
        assert board_name(url) == "acme"


@patch("apps.ingestion.connectors.job_boards.requests.get")
class TestConnectors:
    def test_greenhouse(self, mock_get, board):
        mock_get.return_value = _json_response(GREENHOUSE)
        items = GreenhouseConnector(board("greenhouse", "https://job-boards.greenhouse.io/acme")).fetch()
        assert mock_get.call_args[0][0] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        first = items[0]
        assert first["description"] == "Work & grow."
        assert first["location"] == "Accra, Ghana" and first["organization"] == "Acme"
        assert first["application_deadline"] == datetime(2026, 11, 30, tzinfo=dt_timezone.utc)

    def test_ashby_skips_unlisted_and_joins_locations(self, mock_get, board):
        mock_get.return_value = _json_response(ASHBY)
        items = AshbyConnector(board("ashby", "https://jobs.ashbyhq.com/acme")).fetch()
        assert [i["title"] for i in items] == ["Analyst"]
        assert items[0]["location"] == "Nairobi, Kenya, Kigali, Rwanda"

    def test_workable(self, mock_get, board):
        mock_get.return_value = _json_response(WORKABLE)
        items = WorkableConnector(board("workable", "https://apply.workable.com/acme/")).fetch()
        assert mock_get.call_args[0][0] == "https://apply.workable.com/api/v1/widget/accounts/acme?details=true"
        assert items[0]["description"].startswith("Acme lends to small firms.")
        assert [s["kind"] for s in items[0]["sections"]] == ["overview", "eligibility", "benefits"]
        assert items[0]["organization"] == "Acme Ltd"
        assert items[0]["location"] == "Lagos, Nigeria"
        assert items[0]["opportunity_url"] == "https://apply.workable.com/j/ABC"

    def test_include_keywords_filter_and_job_category(self, mock_get, board):
        mock_get.return_value = _json_response(GREENHOUSE)
        source = board("greenhouse", "https://job-boards.greenhouse.io/acme", keywords="Ghana, Kenya")
        log = run_fetch(source)
        assert (log.items_found, log.items_created) == (2, 1)
        opp = Opportunity.objects.get()
        assert opp.title == "Field Officer" and opp.category == source.category


class TestFindDeadline:
    @pytest.mark.parametrize("text, expected", [
        ("Deadline: October 27, 2026 Applications are open", (2026, 10, 27)),
        ("Deadline: November, 12, 2026", (2026, 11, 12)),
        ("Deadline: December 2nd, 2026", (2026, 12, 2)),
        ("Application deadline: 8 November 2026 at 23:59", (2026, 11, 8)),
        ("Closing date: 15th of January, 2027", (2027, 1, 15)),
    ])
    def test_formats(self, text, expected):
        assert find_deadline(text).date() == datetime(*expected).date()

    @pytest.mark.parametrize("text", ["", "No deadline stated", "Published October 27, 2026", "Deadline: Feb 30, 2026"])
    def test_none(self, text):
        assert find_deadline(text) is None



@pytest.mark.django_db
class TestSetupFetchSources:
    def test_creates_once_and_keeps_admin_edits(self):
        call_command("setup_categories")
        call_command("setup_fetch_sources")
        count = FetchSource.objects.count()
        assert count > 10
        FetchSource.objects.filter(name="Moniepoint").update(is_active=False)

        call_command("setup_fetch_sources")
        assert FetchSource.objects.count() == count
        assert not FetchSource.objects.get(name="Moniepoint").is_active
