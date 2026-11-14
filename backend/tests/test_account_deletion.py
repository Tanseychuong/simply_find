"""Self-service account deletion follows the Privacy notice: deactivate now,
hold 14 days (restorable), then delete everything and say so by email."""

import os
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.deletion import DELETION_HOLD, restore
from apps.accounts.models import User
from apps.companies.models import ApplicationAnswer, Company
from apps.opportunities.models import Opportunity

URL = "/api/auth/me/delete/"


def _request(client, user, password="testpass123", capture=None):
    client.force_authenticate(user)
    return client.post(URL, {"password": password}, format="json")


class TestRequestingDeletion:
    def test_wrong_password_changes_nothing(self, api_client, user):
        res = _request(api_client, user, password="nope")
        user.refresh_from_db()
        assert res.status_code == 400 and user.is_active and user.deletion_requested_at is None

    def test_deactivates_immediately_and_emails(self, api_client, user, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = _request(api_client, user)
        user.refresh_from_db()
        assert res.status_code == 200 and not user.is_active and user.deletion_requested_at
        assert mail.outbox[0].to == [user.email] and "14 days" in mail.outbox[0].body

    def test_cannot_sign_in_afterwards(self, api_client, user):
        _request(api_client, user)
        api_client.force_authenticate(None)
        res = api_client.post("/api/auth/login/", {"email": user.email, "password": "testpass123"}, format="json")
        assert res.status_code == 401

    def test_existing_token_stops_working(self, api_client, user):
        token = api_client.post("/api/auth/login/", {"email": user.email, "password": "testpass123"},
                                format="json").cookies["sf_access"].value
        _request(api_client, user)
        api_client.force_authenticate(None)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert api_client.get("/api/auth/me/").status_code == 401

    def test_admins_cannot_self_delete(self, api_client, admin_user):
        assert _request(api_client, admin_user).status_code == 403
        admin_user.refresh_from_db()
        assert admin_user.is_active

    def test_owned_company_is_suspended(self, api_client, user):
        company = Company.objects.create_with_owner(user, name="Acme", status=Company.Status.APPROVED, is_verified=True)
        _request(api_client, user)
        company.refresh_from_db()
        assert company.status == "suspended" and not company.is_verified


class TestPurging:
    def test_nothing_deleted_during_the_hold(self, api_client, user):
        _request(api_client, user)
        call_command("purge_deleted_accounts")
        assert User.objects.filter(pk=user.pk).exists()

    def test_restored_account_is_never_purged(self, api_client, user):
        _request(api_client, user)
        restore(User.objects.get(pk=user.pk))
        call_command("purge_deleted_accounts")
        assert User.objects.get(pk=user.pk).is_active

    def test_deletes_everything_after_the_hold(self, api_client, user, category, settings,
                                               django_capture_on_commit_callbacks):
        listing = Opportunity.objects.create(title="Mine", description="x", category=category, posted_by=user)
        # an application with a stored file
        owner = User.objects.create_user(email="hr@x.test", name="HR", password="testpass123")
        company = Company.objects.create_with_owner(owner, name="Acme", status="approved", is_verified=True)
        job = Opportunity.objects.create(title="Job", description="x", category=category, company=company,
                                         posted_by=owner, application_method="in_app")
        job.approve(owner)
        req = job.requirements.create(label="CV", kind="file")
        api_client.force_authenticate(user)
        api_client.post("/api/applications/", {"opportunity": job.pk, "consent": "true",
                                               f"answer_{req.pk}": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv")},
                        format="multipart")
        stored = ApplicationAnswer.objects.get().file.path
        assert os.path.exists(stored)

        _request(api_client, user)
        User.objects.filter(pk=user.pk).update(deletion_requested_at=timezone.now() - DELETION_HOLD - timedelta(minutes=1))
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            call_command("purge_deleted_accounts")

        assert not User.objects.filter(pk=user.pk).exists()
        assert not Opportunity.objects.filter(pk=listing.pk).exists()
        assert not ApplicationAnswer.objects.exists() and not os.path.exists(stored)
        assert Opportunity.objects.filter(pk=job.pk).exists()  # other people's data stays
        assert mail.outbox[-1].to == [user.email] and "deleted" in mail.outbox[-1].subject

    def test_admin_restore_action(self, admin_client, user, api_client):
        _request(api_client, user)
        res = admin_client.post("/admin/accounts/user/", {"action": "restore_account", "_selected_action": [user.pk]})
        assert res.status_code == 302
        user.refresh_from_db()
        assert user.is_active and user.deletion_requested_at is None
