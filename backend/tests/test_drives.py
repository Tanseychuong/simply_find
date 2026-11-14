"""Recruitment drives: QR link, desk signups, claiming, and cleanup."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company
from apps.documents.models import Document
from apps.drives.models import DriveRegistration, RecruitmentDrive
from apps.opportunities.models import Opportunity

TODAY = timezone.localdate()


@pytest.fixture
def hr(db):
    return User.objects.create_user(email="hr@acme.test", name="Acme HR", password="testpass123")


@pytest.fixture
def hr_client(hr):
    c = APIClient()
    c.force_authenticate(hr)
    return c


@pytest.fixture
def company(hr):
    return Company.objects.create_with_owner(hr, name="Acme Ltd", status="approved", is_verified=True)


@pytest.fixture
def job(company, category):
    return Opportunity.objects.create(title="Data Intern", description="x", category=category, company=company,
                                      status="approved", published_at=timezone.now(), role_type="internship")


@pytest.fixture
def drive(hr_client, company, job):
    res = hr_client.post("/api/drives/mine/", {
        "name": "University of Juba careers day", "location": "Juba", "starts_on": TODAY.isoformat(),
        "ends_on": TODAY.isoformat(), "opportunities": [job.pk],
    }, format="json")
    assert res.status_code == 201, res.data
    return RecruitmentDrive.objects.get(pk=res.data["id"])


def _signup(hr_client, drive, **extra):
    data = {"name": "Nyandeng Garang", "email": "nyandeng@example.com", "institution": "University of Juba",
            "programme": "BA Economics", "graduation_year": TODAY.year + 1, "status": "student", "consent": True}
    data.update(extra)
    return hr_client.post(f"/api/drives/mine/{drive.pk}/students/", data, format="json")


def _claim_token():
    body = mail.outbox[-1].body
    return re.search(r"claim\?token=(\S+)", body).group(1)


class TestDrives:
    def test_create_gives_code_link_and_qr(self, hr_client, drive):
        assert re.fullmatch(r"[A-HJKMNP-Z2-9]{6}", drive.code)
        assert drive.public_url.endswith(f"/d/{drive.code}")
        qr = hr_client.get(f"/api/drives/mine/{drive.pk}/qr.png")
        assert qr.status_code == 200 and qr["Content-Type"] == "image/png" and qr.content[:4] == b"\x89PNG"

    def test_public_page_lists_open_jobs(self, drive, job, db):
        res = APIClient().get(f"/api/drives/{drive.code.lower()}/")
        assert res.status_code == 200 and res.data["company"]["name"] == "Acme Ltd"
        assert [j["title"] for j in res.data["jobs"]] == ["Data Intern"]
        drive.is_active = False
        drive.save()
        assert APIClient().get(f"/api/drives/{drive.code}/").status_code == 404

    def test_only_own_jobs_can_be_attached(self, hr_client, company, category):
        other = Opportunity.objects.create(title="Not ours", description="x", category=category, status="approved")
        res = hr_client.post("/api/drives/mine/", {"name": "Fair", "starts_on": TODAY.isoformat(),
                                                   "ends_on": TODAY.isoformat(), "opportunities": [other.pk]},
                             format="json")
        assert res.status_code == 400

    def test_dates_checked(self, hr_client, company):
        res = hr_client.post("/api/drives/mine/", {"name": "Fair", "starts_on": TODAY.isoformat(),
                                                   "ends_on": (TODAY - timedelta(days=1)).isoformat()}, format="json")
        assert res.status_code == 400

    def test_other_companies_cannot_see_it(self, drive, db):
        rival = User.objects.create_user(email="r@r.test", name="R", password="testpass123")
        Company.objects.create_with_owner(rival, name="Rival", status="approved")
        c = APIClient()
        c.force_authenticate(rival)
        assert c.get(f"/api/drives/mine/{drive.pk}/").status_code == 404
        assert c.get(f"/api/drives/mine/{drive.pk}/students/").status_code == 404

    def test_self_signup_from_the_link_is_recorded(self, drive, db):
        res = APIClient().post("/api/auth/register/", {"name": "Deng", "email": "deng@example.com",
                                                       "password": "a-long-passphrase", "drive": drive.code},
                               format="json")
        assert res.status_code == 201
        registration = DriveRegistration.objects.get()
        assert registration.method == "self" and registration.claimed_at is not None


class TestDeskSignup:
    def test_signup_upload_claim(self, hr_client, drive, hr, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = _signup(hr_client, drive)
        assert res.status_code == 201, res.data
        student = User.objects.get(email="nyandeng@example.com")
        assert not student.has_usable_password() and student.student_profile.institution == "University of Juba"
        assert "Acme Ltd" in mail.outbox[-1].body

        upload = hr_client.post(
            f"/api/drives/mine/{drive.pk}/students/{res.data['id']}/documents/",
            {"kind": "transcript", "file": SimpleUploadedFile("t.pdf", b"%PDF-1.4 t")}, format="multipart",
        )
        assert upload.status_code == 201 and upload.data["uploaded_by_someone_else"] is True
        assert Document.objects.get().consent_at is None

        token = _claim_token()
        preview = APIClient().get("/api/drives/claim/", {"token": token})
        assert preview.status_code == 200 and preview.data["company"] == "Acme Ltd"
        assert len(preview.data["documents"]) == 1

        assert APIClient().post("/api/drives/claim/", {"token": token, "password": "short"},
                                format="json").status_code == 400
        claimed = APIClient().post("/api/drives/claim/", {"token": token, "password": "a-long-passphrase"},
                                   format="json")
        assert claimed.status_code == 200 and claimed.data["user"]["email_verified"] is True
        assert "sf_access" in claimed.cookies
        student.refresh_from_db()
        assert student.check_password("a-long-passphrase")
        assert Document.objects.get().consent_at is not None
        # One use only, and the team can't add files any more.
        assert APIClient().post("/api/drives/claim/", {"token": token, "password": "another-passphrase"},
                                format="json").status_code == 400
        late = hr_client.post(f"/api/drives/mine/{drive.pk}/students/{res.data['id']}/documents/",
                              {"kind": "cv", "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4 c")}, format="multipart")
        assert late.status_code == 400

    def test_consent_required_and_existing_email_refused(self, hr_client, drive, hr):
        assert _signup(hr_client, drive, consent=False).status_code == 400
        res = _signup(hr_client, drive, email="HR@acme.test")
        assert res.status_code == 400 and drive.code in str(res.data)

    def test_profile_values_are_validated(self, hr_client, drive):
        assert _signup(hr_client, drive, graduation_year=1800).status_code == 400
        assert not User.objects.filter(email="nyandeng@example.com").exists()

    def test_desk_upload_only_on_the_day(self, hr_client, drive):
        reg_id = _signup(hr_client, drive).data["id"]
        DriveRegistration.objects.filter(pk=reg_id).update(created_at=timezone.now() - timedelta(hours=25))
        res = hr_client.post(f"/api/drives/mine/{drive.pk}/students/{reg_id}/documents/",
                             {"kind": "cv", "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4 c")}, format="multipart")
        assert res.status_code == 400

    def test_unclaimed_accounts_are_deleted(self, hr_client, drive, django_capture_on_commit_callbacks):
        reg_id = _signup(hr_client, drive).data["id"]
        _signup(hr_client, drive, email="fresh@example.com")
        DriveRegistration.objects.filter(pk=reg_id).update(created_at=timezone.now() - timedelta(days=15))
        call_command("purge_unclaimed_signups")
        assert not User.objects.filter(email="nyandeng@example.com").exists()
        assert User.objects.filter(email="fresh@example.com").exists()

    def test_listing(self, hr_client, drive):
        _signup(hr_client, drive)
        res = hr_client.get(f"/api/drives/mine/{drive.pk}/students/")
        assert res.data[0]["registered_by_name"] == "Acme HR" and res.data[0]["claimed_at"] is None
        assert hr_client.get(f"/api/drives/mine/{drive.pk}/").data["registration_count"] == 1
