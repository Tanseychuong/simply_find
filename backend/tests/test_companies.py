"""Company accounts: approval, the verified badge, job posting and in-app applications."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Application, Company
from apps.opportunities.models import Opportunity


@pytest.fixture(autouse=True)
def _temp_uploads(settings, tmp_path):
    # Uploads go to a temp dir.
    settings.MEDIA_ROOT = tmp_path
    fs = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    settings.STORAGES = {**settings.STORAGES, "default": fs, "applications": fs}


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="hr@acme.test", name="Acme HR", password="testpass123")


@pytest.fixture
def owner_client(owner):
    # Its own client: sharing api_client would let one force_authenticate
    # silently switch the other's user.
    client = APIClient()
    client.force_authenticate(owner)
    return client


def _company(owner, status=Company.Status.APPROVED, verified=False):
    return Company.objects.create_with_owner(owner, name="Acme Ltd", status=status, is_verified=verified)


def _job_payload(category, **extra):
    return {
        "title": "Junior Analyst", "description": "Analyse things.", "category": category.id,
        "application_method": "in_app",
        "requirements": [
            {"label": "CV", "kind": "file", "required": True},
            {"label": "Why us?", "kind": "long_text", "required": True},
            {"label": "Work mode", "kind": "choice", "options": ["Remote", "On-site"], "required": False},
        ],
        **extra,
    }


class TestCompanySignup:
    def test_registration_starts_pending_and_shows_on_me(self, owner_client):
        res = owner_client.post("/api/companies/", {"name": "Acme Ltd", "website": "https://acme.test", "accept_terms": True}, format="json")
        assert res.status_code == 201
        assert res.data["status"] == "pending" and res.data["can_post"] is False
        assert res.data["slug"] == "acme-ltd"
        me = owner_client.get("/api/auth/me/")
        assert me.data["company"]["status"] == "pending"

    def test_one_company_per_account(self, owner_client, owner):
        _company(owner)
        res = owner_client.post("/api/companies/", {"name": "Second", "accept_terms": True}, format="json")
        assert res.status_code == 400

    def test_cannot_self_approve(self, owner_client, owner):
        _company(owner, status=Company.Status.PENDING)
        owner_client.patch("/api/companies/me/", {"status": "approved", "is_verified": True}, format="json")
        company = Company.objects.get(memberships__user=owner)
        assert company.status == "pending" and company.is_verified is False

    def test_rejected_company_editing_profile_goes_back_to_queue(self, owner_client, owner):
        _company(owner, status=Company.Status.REJECTED)
        owner_client.patch("/api/companies/me/", {"description": "More detail"}, format="json")
        assert Company.objects.get(memberships__user=owner).status == "pending"

    def test_verifying_also_approves(self, owner, admin_user):
        company = _company(owner, status=Company.Status.PENDING)
        company.set_verified(admin_user, True)
        assert company.status == "approved" and company.publishes_directly


class TestPostingJobs:
    def test_pending_company_cannot_post(self, owner_client, owner, category):
        _company(owner, status=Company.Status.PENDING)
        res = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json")
        assert res.status_code == 403

    def test_unverified_company_job_waits_for_moderation(self, owner_client, owner, category, api_client):
        _company(owner)
        res = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json")
        assert res.status_code == 201 and res.data["status"] == "pending"
        assert len(res.data["requirements"]) == 3
        job = Opportunity.objects.get(pk=res.data["id"])
        assert job.source_type == "company" and job.organization == "Acme Ltd"

    def test_verified_company_job_publishes_directly(self, owner_client, owner, category):
        _company(owner, verified=True)
        res = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json")
        assert res.data["status"] == "approved"
        feed = owner_client.get("/api/opportunities/")
        listed = feed.data["results"][0]
        assert listed["company"]["is_verified"] is True and listed["application_method"] == "in_app"

    def test_external_job_needs_a_link(self, owner_client, owner, category):
        _company(owner)
        payload = _job_payload(category, application_method="external", requirements=[])
        assert owner_client.post("/api/companies/me/jobs/", payload, format="json").status_code == 400

    def test_choice_requirement_needs_options(self, owner_client, owner, category):
        _company(owner)
        payload = _job_payload(category, requirements=[{"label": "Pick", "kind": "choice", "options": ["Only one"]}])
        assert owner_client.post("/api/companies/me/jobs/", payload, format="json").status_code == 400

    def test_public_profile_lists_live_jobs_only_for_approved(self, owner_client, owner, category, api_client):
        _company(owner, verified=True)
        owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json")
        res = api_client.get("/api/companies/acme-ltd/")
        assert res.status_code == 200 and len(res.data["jobs"]) == 1
        Company.objects.filter(memberships__user=owner).update(status=Company.Status.SUSPENDED)
        assert api_client.get("/api/companies/acme-ltd/").status_code == 404


@pytest.fixture
def live_job(owner_client, owner, category):
    _company(owner, verified=True)
    res = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json")
    return Opportunity.objects.get(pk=res.data["id"])


class TestApplying:
    def _answers(self, job, **override):
        reqs = {r.label: r.pk for r in job.requirements.all()}
        data = {
            "opportunity": job.pk,
            "consent": "true",
            f"answer_{reqs['CV']}": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf"),
            f"answer_{reqs['Why us?']}": "Because.",
            f"answer_{reqs['Work mode']}": "Remote",
        }
        data.update(override)
        return data

    def test_detail_exposes_requirements(self, api_client, live_job):
        res = api_client.get(f"/api/opportunities/{live_job.pk}/")
        assert [r["label"] for r in res.data["requirements"]] == ["CV", "Why us?", "Work mode"]

    def test_apply_then_company_reviews(self, api_client, user, live_job, owner_client):
        api_client.force_authenticate(user)
        res = api_client.post("/api/applications/", self._answers(live_job), format="multipart")
        assert res.status_code == 201, res.data
        assert api_client.get(f"/api/opportunities/{live_job.pk}/").data["has_applied"] is True

        apps = owner_client.get(f"/api/companies/me/jobs/{live_job.pk}/applications/")
        assert apps.status_code == 200
        application = apps.data["results"][0] if "results" in apps.data else apps.data[0]
        assert application["applicant"]["email"] == user.email
        cv = next(a for a in application["answers"] if a["kind"] == "file")
        assert cv["has_file"] and cv["original_filename"] == "cv.pdf"

        download = owner_client.get(f"/api/applications/answers/{cv['id']}/file/")
        assert download.status_code == 200 and b"".join(download.streaming_content).startswith(b"%PDF")

        upd = owner_client.patch(f"/api/companies/me/applications/{application['id']}/", {"status": "shortlisted"}, format="json")
        assert upd.status_code == 200 and upd.data["status"] == "shortlisted"

    def test_missing_required_answer_is_rejected(self, api_client, user, live_job):
        api_client.force_authenticate(user)
        reqs = {r.label: r.pk for r in live_job.requirements.all()}
        data = self._answers(live_job)
        data.pop(f"answer_{reqs['CV']}")
        res = api_client.post("/api/applications/", data, format="multipart")
        assert res.status_code == 400 and f"answer_{reqs['CV']}" in res.data

    def test_invalid_choice_and_file_type(self, api_client, user, live_job):
        api_client.force_authenticate(user)
        reqs = {r.label: r.pk for r in live_job.requirements.all()}
        bad_choice = self._answers(live_job, **{f"answer_{reqs['Work mode']}": "Mars"})
        assert api_client.post("/api/applications/", bad_choice, format="multipart").status_code == 400
        bad_file = self._answers(live_job, **{f"answer_{reqs['CV']}": SimpleUploadedFile("x.exe", b"MZ")})
        assert api_client.post("/api/applications/", bad_file, format="multipart").status_code == 400

    def test_cannot_apply_twice_or_to_own_job(self, api_client, user, live_job, owner_client):
        api_client.force_authenticate(user)
        assert api_client.post("/api/applications/", self._answers(live_job), format="multipart").status_code == 201
        assert api_client.post("/api/applications/", self._answers(live_job), format="multipart").status_code == 400
        own = owner_client.post("/api/applications/", self._answers(live_job), format="multipart")
        assert own.status_code == 400 and "own company" in str(own.data)

    def test_files_are_private(self, api_client, user, live_job):
        api_client.force_authenticate(user)
        api_client.post("/api/applications/", self._answers(live_job), format="multipart")
        answer_id = Application.objects.get().answers.get(kind="file").pk
        stranger = User.objects.create_user(email="x@x.test", name="X", password="testpass123")
        api_client.force_authenticate(stranger)
        assert api_client.get(f"/api/applications/answers/{answer_id}/file/").status_code == 404

    def test_other_company_cannot_see_applications(self, api_client, live_job):
        other = User.objects.create_user(email="o@o.test", name="O", password="testpass123")
        _company(other)
        api_client.force_authenticate(other)
        assert api_client.get(f"/api/companies/me/jobs/{live_job.pk}/applications/").status_code == 404

    def test_closed_job_rejects_applications(self, api_client, user, live_job, owner_client):
        owner_client.post(f"/api/companies/me/jobs/{live_job.pk}/close/")
        api_client.force_authenticate(user)
        assert api_client.post("/api/applications/", self._answers(live_job), format="multipart").status_code == 400


class TestSitemap:
    def test_lists_public_pages_only(self, api_client, live_job, category, owner):
        hidden = Opportunity.objects.create(title="Pending", description="x", category=category)
        res = api_client.get("/sitemap.xml")
        body = res.content.decode()
        assert res.status_code == 200 and res["Content-Type"] == "application/xml"
        assert f"https://globalopportunities.live/opportunities/{live_job.pk}</loc>" in body
        assert "/companies/acme-ltd</loc>" in body
        assert "/opportunities?category=jobs</loc>" in body
        assert f"/opportunities/{hidden.pk}</loc>" not in body
