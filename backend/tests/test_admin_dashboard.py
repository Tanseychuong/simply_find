from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.opportunities.models import Opportunity


@pytest.mark.django_db
class TestAdminDashboard:
    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_superuser_sees_queue_and_numbers(self, admin_user, category):
        Opportunity.objects.create(category=category, title="Needs a look", description="d", organization="Acme")
        live = Opportunity.objects.create(
            category=category, title="Live one", description="d", organization="Beta",
            application_deadline=timezone.now() + timedelta(days=3),
        )
        live.approve(admin_user)
        Opportunity.objects.filter(pk=live.pk).update(free_access_at=timezone.now() - timedelta(minutes=1))

        response = self._client(admin_user).get("/admin/")
        assert response.status_code == 200
        dash = response.context["dash"]
        assert dash["pending_count"] == 1
        assert dash["live_count"] == 1
        assert [o.title for o in dash["closing"]] == ["Live one"]
        assert dash["users"]["total"] == 1
        body = response.content.decode()
        assert "Needs a look" in body and "Awaiting review" in body
        assert "Manage" in body   # the regular model list is still there

    def test_staff_without_view_permissions_gets_no_sections(self, moderator_user):
        response = self._client(moderator_user).get("/admin/")
        assert response.status_code == 200
        dash = response.context["dash"]
        assert "pending_count" not in dash and "users" not in dash and "sources" not in dash
