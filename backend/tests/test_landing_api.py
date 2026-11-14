"""
The public data the landing page is built from: stats, categories with
live counts, search, page size, and the "still open" rule.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.opportunities.models import Opportunity, OpportunityCategory


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _live(category, admin_user, **fields):
    """An approved, live opportunity."""
    defaults = {"title": "Listing", "description": "Details.", "organization": "Org"}
    opportunity = Opportunity.objects.create(category=category, **{**defaults, **fields})
    opportunity.approve(admin_user)
    return opportunity


@pytest.mark.django_db
class TestStats:
    def test_public_and_counts_only_what_visitors_can_see(self, api_client, category, admin_user):
        _live(category, admin_user, organization="Org A")
        _live(category, admin_user, organization="Org B")
        _live(category, admin_user, organization="Org B")
        Opportunity.objects.create(category=category, title="Pending", description="x")  # not counted

        response = api_client.get("/api/opportunities/stats/")

        assert response.status_code == 200
        assert response.data["live"] == 3
        assert response.data["organizations"] == 2
        assert response.data["categories"] == 1



@pytest.mark.django_db
class TestCategories:
    def test_live_count_and_busiest_first(self, api_client, category, admin_user):
        quiet = OpportunityCategory.objects.create(slug="grants", name="Grants")
        _live(category, admin_user)
        _live(category, admin_user)
        _live(quiet, admin_user)

        response = api_client.get("/api/opportunities/categories/")

        assert response.status_code == 200
        assert [c["slug"] for c in response.data] == ["jobs", "grants"]  # unpaginated list
        assert response.data[0]["live_count"] == 2


@pytest.mark.django_db
class TestFeed:
    def test_expired_listings_are_hidden_from_the_feed(self, api_client, category, admin_user):
        _live(category, admin_user, title="Open")
        _live(category, admin_user, title="Closed", application_deadline=timezone.now() - timedelta(days=1))

        titles = [o["title"] for o in api_client.get("/api/opportunities/").data["results"]]

        assert titles == ["Open"]

    def test_expired_listing_is_still_retrievable_by_id(self, api_client, category, admin_user):
        closed = _live(category, admin_user, application_deadline=timezone.now() - timedelta(days=1))

        response = api_client.get(f"/api/opportunities/{closed.id}/")

        assert response.status_code == 200
        assert response.data["is_open"] is False

    def test_server_side_search(self, api_client, category, admin_user):
        _live(category, admin_user, title="Climate Fellowship")
        _live(category, admin_user, title="Coding Bootcamp", organization="Ashesi")

        by_title = api_client.get("/api/opportunities/", {"search": "climate"}).data["results"]
        by_org = api_client.get("/api/opportunities/", {"search": "ashesi"}).data["results"]

        assert [o["title"] for o in by_title] == ["Climate Fellowship"]
        assert [o["title"] for o in by_org] == ["Coding Bootcamp"]

    def test_page_size_is_honoured_and_capped(self, api_client, category, admin_user, settings):
        for i in range(5):
            _live(category, admin_user, title=f"L{i}")

        small = api_client.get("/api/opportunities/", {"page_size": 2}).data
        huge = api_client.get("/api/opportunities/", {"page_size": 100000}).data

        assert len(small["results"]) == 2 and small["count"] == 5
        assert len(huge["results"]) == 5  # capped at MAX_PAGE_SIZE, not an error

    def test_closing_soon_ordering(self, api_client, category, admin_user):
        now = timezone.now()
        _live(category, admin_user, title="Later", application_deadline=now + timedelta(days=30))
        _live(category, admin_user, title="Soon", application_deadline=now + timedelta(days=2))
        _live(category, admin_user, title="No deadline")

        results = api_client.get("/api/opportunities/", {"ordering": "application_deadline"}).data["results"]

        assert [o["title"] for o in results] == ["Soon", "Later", "No deadline"]

    def test_card_fields_present(self, api_client, category, admin_user, user):
        _live(category, admin_user, image_url="https://cdn.example/a.jpg")
        api_client.force_authenticate(user=user)

        item = api_client.get("/api/opportunities/").data["results"][0]

        assert item["image_url"] == "https://cdn.example/a.jpg"
        assert item["is_open"] is True
        assert item["is_saved"] is False


@pytest.mark.django_db
def test_public_listing_does_not_expose_poster_email(api_client, admin_user, category):
    opp = Opportunity.objects.create(category=category, title="Mine", description="d", posted_by=admin_user)
    opp.approve(admin_user)
    body = api_client.get(f"/api/opportunities/{opp.pk}/").json()
    assert body["posted_by"] == {"id": admin_user.pk, "name": "Admin", "profile_picture": None}
