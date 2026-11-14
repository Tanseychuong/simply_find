"""
Premium is frozen (PREMIUM_ENABLED=False, the production default): there
is no early-access window, so everyone — signed in or not — sees a listing
the moment it's approved, and nobody is reported as Premium.
"""

import pytest

from apps.opportunities.models import Opportunity


@pytest.fixture(autouse=True)
def _premium_frozen(settings, _premium_enabled):
    settings.PREMIUM_ENABLED = False


@pytest.fixture
def pending_opportunity(db, user, category):
    return Opportunity.objects.create(
        posted_by=user, category=category, title="Pending Job", description="A job.",
    )


def _titles(response):
    return [o["title"] for o in response.data["results"]]


@pytest.mark.django_db
class TestPremiumFrozen:
    def test_anonymous_sees_listing_right_after_approval(self, api_client, admin_user, pending_opportunity):
        pending_opportunity.approve(admin_user)

        assert pending_opportunity.title in _titles(api_client.get("/api/opportunities/"))
        assert api_client.get(f"/api/opportunities/{pending_opportunity.id}/").status_code == 200

    def test_free_user_sees_listing_right_after_approval(self, api_client, admin_user, pending_opportunity, user):
        pending_opportunity.approve(admin_user)

        api_client.force_authenticate(user=user)
        assert pending_opportunity.title in _titles(api_client.get("/api/opportunities/"))

    def test_pending_is_still_hidden(self, api_client, pending_opportunity):
        assert pending_opportunity.title not in _titles(api_client.get("/api/opportunities/"))
        assert not Opportunity.visible_to(None).filter(pk=pending_opportunity.pk).exists()

    def test_approval_still_records_the_free_window(self, admin_user, pending_opportunity):
        """So unfreezing later needs no backfill."""
        pending_opportunity.approve(admin_user)
        assert pending_opportunity.free_access_at > pending_opportunity.published_at

    def test_premium_flag_is_not_reported(self, api_client, premium_user):
        api_client.force_authenticate(user=premium_user)
        assert api_client.get("/api/auth/me/").data["is_premium_active"] is False

    def test_stats_count_new_listings_and_say_premium_is_off(self, api_client, admin_user, pending_opportunity):
        pending_opportunity.approve(admin_user)

        data = api_client.get("/api/opportunities/stats/").data

        assert data["live"] == 1
        assert data["premium_enabled"] is False
        assert data["early_access_hours"] == 0


@pytest.mark.django_db
def test_unfreezing_restores_the_window(settings, api_client, admin_user, pending_opportunity, user):
    settings.PREMIUM_ENABLED = True
    pending_opportunity.approve(admin_user)

    api_client.force_authenticate(user=user)
    assert pending_opportunity.title not in _titles(api_client.get("/api/opportunities/"))
