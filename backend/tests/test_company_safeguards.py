"""Safeguards around company hiring: consent, hiring commitments, protected-
characteristic questions, re-review on edit, suspension, moderator review,
notifications that never leak answers, file deletion, logo upload, retention."""

import io
import os
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.companies.models import Application, ApplicationAnswer, Company
from apps.companies.services import flagged_terms, review_company
from apps.opportunities.models import Opportunity

# Shared fixtures/helpers (pytest picks up imported fixtures).
from tests.test_companies import _company, _job_payload, _temp_uploads, live_job, owner, owner_client  # noqa: F401


def _apply(client, job, **override):
    reqs = {r.label: r.pk for r in job.requirements.all()}
    data = {"opportunity": job.pk, "consent": "true"}
    if "CV" in reqs:
        data[f"answer_{reqs['CV']}"] = SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf")
    if "Why us?" in reqs:
        data[f"answer_{reqs['Why us?']}"] = "Because."
    data.update(override)
    return client.post("/api/applications/", data, format="multipart")


class TestConsentAndTerms:
    def test_company_signup_needs_terms(self, owner_client):
        res = owner_client.post("/api/companies/", {"name": "Acme Ltd"}, format="json")
        assert res.status_code == 400 and "accept_terms" in res.data

    def test_terms_time_is_recorded(self, owner_client, owner):
        owner_client.post("/api/companies/", {"name": "Acme Ltd", "accept_terms": True}, format="json")
        assert Company.objects.get(memberships__user=owner).terms_accepted_at is not None

    def test_application_needs_consent(self, api_client, user, live_job):
        api_client.force_authenticate(user)
        res = _apply(api_client, live_job, consent="false")
        assert res.status_code == 400 and "consent" in res.data
        assert _apply(api_client, live_job).status_code == 201
        assert Application.objects.get().consent_at is not None

    def test_reserved_slug(self, owner):
        assert Company.objects.create_with_owner(owner, name="Me").slug == "me-company"


class TestSensitiveRequirements:
    def test_verified_company_job_is_held(self, owner_client, owner, category, django_capture_on_commit_callbacks):
        _company(owner, verified=True)
        payload = _job_payload(category, requirements=[{"label": "What is your date of birth?", "kind": "short_text"}])
        with django_capture_on_commit_callbacks(execute=True):
            res = owner_client.post("/api/companies/me/jobs/", payload, format="json")
        assert res.data["status"] == "pending" and res.data["flagged_terms"] == ["age"]
        assert any("quick review" in m.subject for m in mail.outbox)

    def test_harmless_requirements_are_not_flagged(self):
        assert flagged_terms([{"label": "Years managing projects", "help_text": "Average team size"}]) == []

    def test_moderation_queue_shows_flags(self, owner_client, owner, category, moderator_user, api_client):
        _company(owner)
        owner_client.post("/api/companies/me/jobs/", _job_payload(
            category, requirements=[{"label": "Your religion", "kind": "short_text"}]), format="json")
        api_client.force_authenticate(moderator_user)
        item = api_client.get("/api/opportunities/pending/").data["results"][0]
        assert item["flagged_terms"] == ["religion"] and item["requirements"][0]["label"] == "Your religion"


class TestEditingJobs:
    def test_unverified_edit_goes_back_to_review(self, owner_client, owner, category, admin_user):
        _company(owner)
        job_id = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json").data["id"]
        Opportunity.objects.get(pk=job_id).approve(admin_user)
        res = owner_client.patch(f"/api/companies/me/jobs/{job_id}/", {"title": "Senior Analyst"}, format="json")
        assert res.status_code == 200 and res.data["status"] == "pending" and res.data["title"] == "Senior Analyst"

    def test_verified_edit_stays_live(self, owner_client, live_job):
        res = owner_client.patch(f"/api/companies/me/jobs/{live_job.pk}/", {"location": "Remote"}, format="json")
        assert res.status_code == 200 and res.data["status"] == "approved"

    def test_requirements_editable_until_someone_applies(self, owner_client, api_client, user, live_job):
        new_reqs = {"requirements": [{"label": "CV", "kind": "file"}, {"label": "Why us?", "kind": "long_text"}]}
        assert owner_client.patch(f"/api/companies/me/jobs/{live_job.pk}/", new_reqs, format="json").status_code == 200
        api_client.force_authenticate(user)
        assert _apply(api_client, live_job).status_code == 201
        res = owner_client.patch(f"/api/companies/me/jobs/{live_job.pk}/", new_reqs, format="json")
        assert res.status_code == 400 and "requirements" in res.data

    def test_company_jobs_not_editable_through_generic_endpoint(self, owner_client, owner, category):
        _company(owner)
        job_id = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json").data["id"]
        assert owner_client.patch(f"/api/opportunities/{job_id}/", {"title": "x"}, format="json").status_code == 404


class TestSuspension:
    def test_suspended_company_jobs_disappear(self, api_client, owner, live_job, admin_user):
        assert api_client.get(f"/api/opportunities/{live_job.pk}/").status_code == 200
        review_company(Company.objects.get(memberships__user=owner), admin_user, "suspend", "Fake listings")
        assert api_client.get(f"/api/opportunities/{live_job.pk}/").status_code == 404
        assert api_client.get("/api/opportunities/").data["count"] == 0


class TestModeratorReview:
    def test_moderator_approves_but_cannot_verify(self, api_client, owner, moderator_user,
                                                 django_capture_on_commit_callbacks):
        company = _company(owner, status=Company.Status.PENDING)
        api_client.force_authenticate(moderator_user)
        assert api_client.get("/api/companies/review/").data["results"][0]["id"] == company.pk
        with django_capture_on_commit_callbacks(execute=True):
            res = api_client.post(f"/api/companies/review/{company.pk}/", {"action": "approve"}, format="json")
        assert res.status_code == 200 and res.data["status"] == "approved"
        assert mail.outbox[-1].to == [owner.email] and "approved" in mail.outbox[-1].subject
        res = api_client.post(f"/api/companies/review/{company.pk}/", {"action": "verify"}, format="json")
        assert res.status_code == 403

    def test_admin_verifies_and_reject_needs_reason(self, api_client, owner, admin_user):
        company = _company(owner, status=Company.Status.PENDING)
        api_client.force_authenticate(admin_user)
        res = api_client.post(f"/api/companies/review/{company.pk}/", {"action": "reject"}, format="json")
        assert res.status_code == 400
        res = api_client.post(f"/api/companies/review/{company.pk}/", {"action": "verify"}, format="json")
        assert res.data["is_verified"] is True

    def test_regular_user_cannot_review(self, api_client, user):
        api_client.force_authenticate(user)
        assert api_client.get("/api/companies/review/").status_code == 403


class TestNotificationsAndPrivacy:
    def test_application_emails_never_contain_answers(self, api_client, user, live_job,
                                                     django_capture_on_commit_callbacks):
        api_client.force_authenticate(user)
        why = live_job.requirements.get(label="Why us?").pk
        with django_capture_on_commit_callbacks(execute=True):
            _apply(api_client, live_job, **{f"answer_{why}": "SECRET-ANSWER"})
        assert len(mail.outbox) == 2
        assert all("SECRET-ANSWER" not in m.body and not m.attachments for m in mail.outbox)

    def test_status_change_emails_applicant(self, api_client, user, live_job, owner_client,
                                           django_capture_on_commit_callbacks):
        api_client.force_authenticate(user)
        app_id = _apply(api_client, live_job).data["id"]
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            owner_client.patch(f"/api/companies/me/applications/{app_id}/", {"status": "shortlisted"}, format="json")
        assert mail.outbox[0].to == [user.email] and "shortlisted" in mail.outbox[0].body

    def test_withdraw_deletes_answers_and_files(self, api_client, user, live_job, owner_client,
                                               django_capture_on_commit_callbacks):
        api_client.force_authenticate(user)
        app_id = _apply(api_client, live_job).data["id"]
        stored = ApplicationAnswer.objects.get(kind="file").file.path
        with django_capture_on_commit_callbacks(execute=True):
            api_client.post(f"/api/applications/{app_id}/withdraw/")
        assert not ApplicationAnswer.objects.exists() and not os.path.exists(stored)
        res = owner_client.patch(f"/api/companies/me/applications/{app_id}/", {"status": "hired"}, format="json")
        assert res.status_code == 404  # the company can no longer touch it

    def test_deleting_account_deletes_files(self, api_client, user, live_job, django_capture_on_commit_callbacks):
        api_client.force_authenticate(user)
        _apply(api_client, live_job)
        stored = ApplicationAnswer.objects.get(kind="file").file.path
        assert os.path.exists(stored)
        with django_capture_on_commit_callbacks(execute=True):
            user.delete()
        assert not os.path.exists(stored)


class TestLogoUpload:
    def test_upload_valid_image(self, owner_client, owner):
        from PIL import Image
        _company(owner)
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, "PNG")
        res = owner_client.post("/api/companies/me/logo/", {"logo": SimpleUploadedFile("l.png", buf.getvalue())},
                                format="multipart")
        assert res.status_code == 200 and "company_logos/acme-ltd" in res.data["logo_url"]

    def test_rejects_fake_image(self, owner_client, owner):
        _company(owner)
        res = owner_client.post("/api/companies/me/logo/", {"logo": SimpleUploadedFile("l.png", b"not an image")},
                                format="multipart")
        assert res.status_code == 400


class TestRetention:
    def test_disabled_by_default_keeps_everything(self, api_client, user, live_job, settings):
        settings.APPLICATION_RETENTION_DAYS = None
        api_client.force_authenticate(user)
        _apply(api_client, live_job)
        call_command("prune_applications")
        assert Application.objects.count() == 1

    def test_prunes_applications_to_long_closed_jobs(self, api_client, user, live_job, settings):
        settings.APPLICATION_RETENTION_DAYS = 30
        api_client.force_authenticate(user)
        _apply(api_client, live_job)
        Opportunity.objects.filter(pk=live_job.pk).update(application_deadline=timezone.now() - timedelta(days=31))
        call_command("prune_applications")
        assert Application.objects.count() == 0


@pytest.mark.parametrize("storages_same, debug, expected", [(True, False, 1), (False, False, 0), (True, True, 0)])
def test_deploy_check_warns_when_cvs_share_public_storage(settings, storages_same, debug, expected):
    from apps.companies.checks import application_files_are_private
    public = {"BACKEND": "x"}
    settings.DEBUG = debug
    settings.STORAGES = {**settings.STORAGES, "default": public,
                         "applications": public if storages_same else {"BACKEND": "y"}}
    assert len(application_files_are_private(None)) == expected
