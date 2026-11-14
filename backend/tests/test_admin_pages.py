from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.ingestion.models import FetchLog, FetchSource
from apps.opportunities.models import Opportunity, SavedOpportunity

CHANGELISTS = [
    "accounts_user", "opportunities_opportunity", "opportunities_opportunitycategory",
    "opportunities_savedopportunity", "ingestion_fetchsource", "ingestion_fetchlog",
]


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def pending(category):
    return Opportunity.objects.create(category=category, title="Pending one", description="d")


@pytest.mark.django_db
class TestPagesRender:
    def test_every_changelist_and_change_page_loads(self, admin_user, category, pending):
        source = FetchSource.objects.create(name="Feed", connector_type="rss", url="https://x.test/rss", category=category)
        now = timezone.now()
        log = FetchLog.objects.create(source=source, started_at=now, finished_at=now, status=FetchLog.Status.FAILURE)
        saved = SavedOpportunity.objects.create(user=admin_user, opportunity=pending)
        objects = {
            "accounts_user": admin_user, "opportunities_opportunity": pending,
            "opportunities_opportunitycategory": category, "opportunities_savedopportunity": saved,
            "ingestion_fetchsource": source, "ingestion_fetchlog": log,
        }
        client = _client(admin_user)
        for name in CHANGELISTS:
            assert client.get(reverse(f"admin:{name}_changelist")).status_code == 200, name
            assert client.get(reverse(f"admin:{name}_change", args=[objects[name].pk])).status_code == 200, name

    def test_status_pill_in_queue(self, admin_user, pending):
        body = _client(admin_user).get(reverse("admin:opportunities_opportunity_changelist")).content.decode()
        assert 'eel-pill--warn">Pending' in body


@pytest.mark.django_db
class TestModerationActions:
    url = staticmethod(lambda: reverse("admin:opportunities_opportunity_changelist"))

    def _act(self, client, action, *pks):
        return client.post(self.url(), {"action": action, "_selected_action": [str(pk) for pk in pks]}, follow=True)

    def test_approve_skips_already_approved(self, admin_user, category, pending):
        live = Opportunity.objects.create(category=category, title="Live", description="d")
        live.approve(admin_user)
        earlier = live.published_at - timedelta(days=1)
        Opportunity.objects.filter(pk=live.pk).update(published_at=earlier)

        self._act(_client(admin_user), "approve_opportunities", pending.pk, live.pk)

        pending.refresh_from_db()
        live.refresh_from_db()
        assert pending.status == Opportunity.Status.APPROVED and pending.published_at is not None
        assert live.published_at == earlier   # publish date not reset

    def test_actions_hidden_without_verify_permission(self, category, pending):
        staff = User.objects.create_user(email="staff@example.com", name="Staff", password="x", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_opportunity", "change_opportunity"]))
        client = _client(staff)

        body = client.get(self.url()).content.decode()
        assert "approve_opportunities" not in body and "reject_opportunities" not in body

        self._act(client, "approve_opportunities", pending.pk)
        pending.refresh_from_db()
        assert pending.status == Opportunity.Status.PENDING


@pytest.mark.django_db
class TestChangeFormStatus:
    def _post(self, client, opp, **overrides):
        data = {
            "title": opp.title, "organization": "", "category": opp.category_id, "description": opp.description,
            "location": "", "opportunity_url": "", "application_deadline_0": "", "application_deadline_1": "",
            "image_url": "", "posted_by": "", "source_type": opp.source_type, "fetch_source": "",
            "status": opp.status, "rejection_reason": "",
        }
        data.update(overrides)
        return client.post(reverse("admin:opportunities_opportunity_change", args=[opp.pk]), data)

    def test_setting_approved_publishes_it(self, moderator_user, pending):
        moderator_user.user_permissions.add(*Permission.objects.filter(codename__in=["view_opportunity", "change_opportunity"]))
        response = self._post(_client(moderator_user), pending, status="approved")
        assert response.status_code == 302
        pending.refresh_from_db()
        assert pending.status == Opportunity.Status.APPROVED
        assert pending.published_at is not None
        assert pending.reviewed_by == moderator_user

    def test_setting_rejected_records_reason(self, admin_user, pending):
        self._post(_client(admin_user), pending, status="rejected", rejection_reason="Expired link")
        pending.refresh_from_db()
        assert pending.status == Opportunity.Status.REJECTED
        assert pending.rejection_reason == "Expired link" and pending.reviewed_by == admin_user

    def test_status_read_only_without_verify_permission(self, category, pending):
        staff = User.objects.create_user(email="staff@example.com", name="Staff", password="x", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_opportunity", "change_opportunity"]))
        self._post(_client(staff), pending, status="approved")
        pending.refresh_from_db()
        assert pending.status == Opportunity.Status.PENDING

