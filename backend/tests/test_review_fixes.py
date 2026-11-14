"""Regression tests for the branch review of 2026-11-06 (one per finding)."""

from unittest import mock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.companies.models import Application, ApplicationAnswer, Company
from apps.companies.services import review_company, submit_application
from apps.opportunities.models import Opportunity, SavedOpportunity
from tests.test_companies import _company, _job_payload, _temp_uploads, live_job, owner, owner_client  # noqa: F401


def _apply(client, job):
    req = job.requirements.get(label="CV")
    why = job.requirements.get(label="Why us?")
    return client.post("/api/applications/", {
        "opportunity": job.pk, "consent": "true",
        f"answer_{req.pk}": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv"), f"answer_{why.pk}": "Because.",
    }, format="multipart")


class TestCors:  # finding 2
    def test_production_sites_always_allowed_and_env_adds_more(self):
        from django.conf import settings
        for origin in ("https://globalopportunities.live", "https://www.globalopportunities.live",
                       "https://eel-web.onrender.com"):
            assert origin in settings.CORS_ALLOWED_ORIGINS
        assert settings.CSRF_TRUSTED_ORIGINS == settings.CORS_ALLOWED_ORIGINS

    def test_reset_links_use_the_canonical_site(self):
        from django.conf import settings
        assert settings.FRONTEND_URL == settings.SITE_URL


class TestIdentityLock:  # finding 3
    def test_approved_company_cannot_rename_itself(self, owner_client, owner):
        _company(owner, verified=True)
        res = owner_client.patch("/api/companies/me/", {"name": "Google", "website": "https://google.com"}, format="json")
        assert res.status_code == 400 and "name" in res.data and "website" in res.data
        assert Company.objects.get(memberships__user=owner).name == "Acme Ltd"

    def test_other_fields_still_editable(self, owner_client, owner):
        _company(owner, verified=True)
        res = owner_client.patch("/api/companies/me/", {"name": "Acme Ltd", "description": "Updated"}, format="json")
        assert res.status_code == 200 and res.data["description"] == "Updated"

    def test_pending_company_can_still_fix_its_name(self, owner_client, owner):
        _company(owner, status=Company.Status.PENDING)
        assert owner_client.patch("/api/companies/me/", {"name": "Acme Limited"}, format="json").status_code == 200


class TestSuspendedCompanyCannotReadApplicants:  # finding 4
    def test_all_applicant_endpoints_blocked(self, api_client, user, live_job, owner_client, owner, admin_user):
        api_client.force_authenticate(user)
        app_id = _apply(api_client, live_job).data["id"]
        file_id = ApplicationAnswer.objects.get(kind="file").pk
        review_company(Company.objects.get(memberships__user=owner), admin_user, "suspend", "Scam")
        assert owner_client.get(f"/api/companies/me/jobs/{live_job.pk}/applications/").status_code == 403
        assert owner_client.patch(f"/api/companies/me/applications/{app_id}/", {"status": "hired"},
                                  format="json").status_code == 403
        assert owner_client.get(f"/api/applications/answers/{file_id}/file/").status_code == 404
        # the applicant still has their own file
        assert api_client.get(f"/api/applications/answers/{file_id}/file/").status_code == 200


class TestEditKeepsPublishDate:  # finding 5
    def test_verified_edit_does_not_redate(self, owner_client, live_job):
        before = Opportunity.objects.get(pk=live_job.pk)
        owner_client.patch(f"/api/companies/me/jobs/{live_job.pk}/", {"title": "Typo fixed"}, format="json")
        after = Opportunity.objects.get(pk=live_job.pk)
        assert after.status == "approved" and after.title == "Typo fixed"
        assert after.published_at == before.published_at


class TestDoubleSubmit:  # finding 6
    def test_race_returns_friendly_error_not_500(self, user, live_job):
        from rest_framework.exceptions import ValidationError
        with mock.patch.object(Application.objects, "create", side_effect=IntegrityError("uq_application_per_job")):
            with pytest.raises(ValidationError) as exc:
                submit_application(user, live_job, {"consent": "true",
                                                    f"answer_{live_job.requirements.get(label='Why us?').pk}": "x",
                                                    }, {f"answer_{live_job.requirements.get(label='CV').pk}":
                                                        SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv")})
        assert "already applied" in str(exc.value.detail)


class TestPasswordResetEndsSessions:  # finding 7
    def test_old_access_and_refresh_tokens_stop_working(self, user):
        client = APIClient()
        tokens = client.post("/api/auth/login/", {"email": user.email, "password": "testpass123"}, format="json").data
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert client.get("/api/auth/me/").status_code == 200

        # Backdate the cut-off check by making the old tokens look a second older.
        from django.utils import timezone
        from datetime import timedelta
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        with mock.patch("apps.accounts.views.timezone.now", return_value=timezone.now() + timedelta(seconds=2)):
            res = APIClient().post("/api/auth/password-reset/confirm/",
                                   {"uid": uid, "token": token, "password": "N3w-Passw0rd!x"}, format="json")
        assert res.status_code == 200

        assert client.get("/api/auth/me/").status_code == 401
        assert APIClient().post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 401

    def test_new_login_after_reset_works(self, user):
        from django.utils import timezone
        user.tokens_valid_after = timezone.now()
        user.save()
        client = APIClient()
        tokens = client.post("/api/auth/login/", {"email": user.email, "password": "testpass123"}, format="json").data
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert client.get("/api/auth/me/").status_code == 200
        assert client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 200


class TestStorageConfig:  # finding 8
    def test_private_bucket_without_s3_media_does_not_crash(self):
        import os
        import subprocess
        import sys
        env = {**os.environ, "DEBUG": "True", "SUPABASE_URL": "https://x.supabase.co",
               "SUPABASE_PRIVATE_BUCKET": "priv", "SUPABASE_STORAGE_BUCKET": ""}
        res = subprocess.run([sys.executable, "-c", "import config.settings as s; print(s.STORAGES['applications']['BACKEND'])"],
                             env=env, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert "FileSystemStorage" in res.stdout


class TestCompanyPageQueries:  # finding 9
    def test_query_count_does_not_grow_with_jobs(self, api_client, user, owner, category, django_assert_max_num_queries):
        company = _company(owner, verified=True)
        for i in range(8):
            o = Opportunity.objects.create(title=f"Job {i}", description="x", category=category, company=company,
                                           posted_by=owner, application_method="external",
                                           opportunity_url="https://acme.test/apply")
            o.approve(owner)
            SavedOpportunity.objects.create(user=user, opportunity=o)
        api_client.force_authenticate(user)
        with django_assert_max_num_queries(6):
            res = api_client.get("/api/companies/acme-ltd/")
        assert len(res.data["jobs"]) == 8 and all(j["is_saved"] for j in res.data["jobs"])


class TestTakedownRebuild:  # finding 10
    def test_suspend_and_reject_live_listing_request_rebuild(self, settings, owner, live_job, admin_user,
                                                             django_capture_on_commit_callbacks):
        settings.FRONTEND_DEPLOY_HOOK = "https://hooks.example/deploy"
        with mock.patch("config.seo.requests.post") as post:
            with django_capture_on_commit_callbacks(execute=True):
                review_company(Company.objects.get(memberships__user=owner), admin_user, "suspend", "Scam")
            assert post.call_count == 1 and post.call_args.args[0] == "https://hooks.example/deploy"

            from apps.opportunities.services import reject_opportunity
            other = Opportunity.objects.create(title="T", description="x", category=live_job.category)
            other.approve(admin_user)
            with django_capture_on_commit_callbacks(execute=True):
                reject_opportunity(other, admin_user, "Spam")
            assert post.call_count == 2

    def test_no_hook_no_request(self, settings, owner, live_job, admin_user, django_capture_on_commit_callbacks):
        settings.FRONTEND_DEPLOY_HOOK = ""
        with mock.patch("config.seo.requests.post") as post:
            with django_capture_on_commit_callbacks(execute=True):
                review_company(Company.objects.get(memberships__user=owner), admin_user, "suspend", "Scam")
        post.assert_not_called()
