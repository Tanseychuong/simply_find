"""Guided profile, document vault, certificates, eligibility, applying from the vault."""

import hashlib
from datetime import date
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Application, Company
from apps.documents.credentials import verify_open_badge
from apps.documents.models import Credential, Document, DocumentAccess
from apps.opportunities.models import Opportunity
from apps.profiles.models import StudentProfile

PDF = b"%PDF-1.4 transcript"
THIS_YEAR = timezone.localdate().year


@pytest.fixture
def student(db):
    return User.objects.create_user(email="akol@example.com", name="Akol Deng", password="testpass123")


@pytest.fixture
def client(student):
    c = APIClient()
    c.force_authenticate(student)
    return c


def _complete_profile(user, **extra):
    fields = dict(date_of_birth=date(2003, 5, 1), country="South Sudan", status="student",
                  institution="University of Juba", programme="BSc Computer Science",
                  graduation_year=THIS_YEAR + 1)
    fields.update(extra)
    profile = StudentProfile.for_user(user)
    for key, value in fields.items():
        setattr(profile, key, value)
    profile.save()
    return profile


def _upload(client, kind="transcript", data=PDF, name="transcript.pdf"):
    return client.post("/api/profile/documents/", {"kind": kind, "title": "Year 3 transcript",
                                                   "file": SimpleUploadedFile(name, data)}, format="multipart")


class TestGuidedProfile:
    def test_new_profile_starts_at_step_one(self, client):
        res = client.get("/api/profile/")
        assert res.status_code == 200
        progress = res.data["progress"]
        assert progress["next_step"] == "about" and progress["completeness"] == 11  # only the name
        assert [s["key"] for s in progress["steps"]] == ["about", "studies", "skills", "documents"]

    def test_steps_fill_up(self, client, category):
        res = client.patch("/api/profile/", {"date_of_birth": "2003-05-01", "country": "South Sudan",
                                             "phone": "+211 912 345 678"}, format="json")
        assert res.status_code == 200 and res.data["progress"]["next_step"] == "studies"
        res = client.patch("/api/profile/", {"status": "student", "institution": "University of Juba",
                                             "programme": "BSc Computer Science", "graduation_year": THIS_YEAR + 1,
                                             "field": category.slug}, format="json")
        assert res.data["progress"]["next_step"] == "skills"
        res = client.patch("/api/profile/", {"skills": ["Excel", "excel", " Python "]}, format="json")
        assert res.data["skills"] == ["Excel", "Python"]
        assert _upload(client).status_code == 201
        res = client.get("/api/profile/")
        assert res.data["progress"]["completeness"] == 100 and res.data["progress"]["next_step"] is None

    def test_name_is_edited_on_the_profile(self, client, student):
        client.patch("/api/profile/", {"name": "Akol M. Deng"}, format="json")
        student.refresh_from_db()
        assert student.name == "Akol M. Deng"

    @pytest.mark.parametrize("payload", [
        {"date_of_birth": "2020-01-01"},
        {"graduation_year": 1900},
        {"phone": "call me"},
        {"skills": ["x" * 41]},
        {"skills": [f"s{i}" for i in range(21)]},
        {"status": "professional"},
    ])
    def test_bad_values_refused(self, client, payload):
        assert client.patch("/api/profile/", payload, format="json").status_code == 400

    def test_signed_out_refused(self, db):
        assert APIClient().get("/api/profile/").status_code == 401


class TestVault:
    def test_upload_list_download_delete(self, client, student):
        res = _upload(client)
        assert res.status_code == 201 and res.data["kind"] == "transcript"
        doc = Document.objects.get()
        assert doc.file.name.startswith("vault/") and "transcript" not in doc.file.name
        assert doc.consent_at is not None and doc.uploaded_by is None
        assert len(client.get("/api/profile/documents/").data) == 1
        download = client.get(f"/api/profile/documents/{doc.pk}/file/")
        assert download.status_code == 200 and b"".join(download.streaming_content) == PDF
        assert download["Cache-Control"] == "private, no-store"
        storage, name = doc.file.storage, doc.file.name
        with django_capture_on_commit():
            assert client.delete(f"/api/profile/documents/{doc.pk}/").status_code == 204
        assert not storage.exists(name)

    def test_others_cannot_see_or_open(self, client, db):
        _upload(client)
        doc = Document.objects.get()
        other = APIClient()
        other.force_authenticate(User.objects.create_user(email="x@x.test", name="X", password="testpass123"))
        assert other.get(f"/api/profile/documents/{doc.pk}/file/").status_code == 404
        assert other.delete(f"/api/profile/documents/{doc.pk}/").status_code == 404
        assert other.get("/api/profile/documents/").data == []

    def test_upload_gate_applies(self, client):
        res = _upload(client, data=b"PK\x03\x04word", name="cv.docx")
        assert res.status_code == 400 and "PDF" in str(res.data)
        assert _upload(client, kind="selfie").status_code == 400

    def test_limit(self, client, student, monkeypatch):
        monkeypatch.setattr(Document, "MAX_PER_USER", 1)
        assert _upload(client).status_code == 201
        assert _upload(client).status_code == 400

    def test_rename(self, client):
        doc_id = _upload(client).data["id"]
        res = client.patch(f"/api/profile/documents/{doc_id}/", {"title": "Final transcript"}, format="json")
        assert res.status_code == 200 and res.data["title"] == "Final transcript"


def django_capture_on_commit():
    """Run on_commit callbacks inside the test transaction."""
    from django.test import TestCase
    return TestCase.captureOnCommitCallbacks(execute=True)


class TestCredentialLinks:
    @pytest.mark.parametrize("provider, url", [
        ("coursera", "https://www.coursera.org/account/accomplishments/verify/ABC123"),
        ("coursera", "https://coursera.org/verify/ABC123"),
        ("edx", "https://courses.edx.org/certificates/0123abcd"),
        ("credly", "https://www.credly.com/badges/1b2c3d4e-0000-4000-8000-000000000000"),
        ("linkedin_learning", "https://www.linkedin.com/learning/certificates/abc123"),
    ])
    def test_provider_certificate_pages_are_recognised(self, client, provider, url):
        res = client.post("/api/profile/credentials/", {"title": "Data Analytics", "url": url}, format="json")
        assert res.status_code == 201, res.data
        assert res.data["provider"] == provider and res.data["check_status"] == "recognised_link"

    @pytest.mark.parametrize("url", [
        "https://coursera.org.evil.example/verify/ABC",   # look-alike domain
        "https://www.coursera.org/learn/python",         # a course page, not a certificate
    ])
    def test_other_pages_are_not(self, client, url):
        res = client.post("/api/profile/credentials/", {"title": "x", "url": url, "provider": "coursera"},
                          format="json")
        assert res.status_code == 201 and res.data["check_status"] == "failed"

    def test_unknown_sites_are_unchecked_and_http_refused(self, client):
        res = client.post("/api/profile/credentials/", {"title": "Workshop", "url": "https://example.org/cert/1"},
                          format="json")
        assert res.data["provider"] == "other" and res.data["check_status"] == "unchecked"
        assert client.post("/api/profile/credentials/", {"title": "x", "url": "http://example.org/c"},
                           format="json").status_code == 400

    def test_duplicates_refused_and_delete(self, client):
        payload = {"title": "Python", "url": "https://coursera.org/verify/ABC"}
        cid = client.post("/api/profile/credentials/", payload, format="json").data["id"]
        assert client.post("/api/profile/credentials/", payload, format="json").status_code == 400
        assert client.delete(f"/api/profile/credentials/{cid}/").status_code == 204


ASSERTION_URL = "https://badges.example.org/assertions/42"


def _assertion(email="akol@example.com", **extra):
    salt = "s4lt"
    data = {
        "@context": "https://w3id.org/openbadges/v2", "type": "Assertion", "id": ASSERTION_URL,
        "recipient": {"type": "email", "hashed": True, "salt": salt,
                      "identity": "sha256$" + hashlib.sha256((email + salt).encode()).hexdigest()},
        "badge": {"type": "BadgeClass", "name": "Digital Skills", "issuer": {"name": "Juba Tech Hub"}},
        "verification": {"type": "hosted"}, "issuedOn": "2026-03-01T00:00:00Z",
    }
    data.update(extra)
    return data


def _fetch_returns(data):
    return mock.patch("apps.documents.credentials.fetch_public_json", return_value=(data, ASSERTION_URL))


class TestOpenBadges:
    def test_badge_for_this_person_is_verified(self, client):
        with _fetch_returns(_assertion()):
            res = client.post("/api/profile/credentials/", {"provider": "open_badge", "url": ASSERTION_URL},
                              format="json")
        assert res.status_code == 201
        assert res.data["check_status"] == "verified"
        assert res.data["title"] == "Digital Skills" and res.data["issuer"] == "Juba Tech Hub"
        assert res.data["issued_on"] == "2026-03-01"

    @pytest.mark.parametrize("assertion, why", [
        (_assertion(email="someone@else.org"), "different email"),
        (_assertion(revoked=True), "revoked"),
        (_assertion(expires="2020-01-01T00:00:00Z"), "expired"),
        (_assertion(id="https://elsewhere.example/a/1"), "hosted where"),
        (_assertion(type="BadgeClass"), "isn't an Open Badge"),
        (_assertion(verification={"type": "SignedBadge"}), "hosted by their issuer"),
    ])
    def test_bad_badges_fail(self, student, assertion, why):
        with _fetch_returns(assertion):
            result = verify_open_badge(ASSERTION_URL, student.email)
        assert result.status == "failed" and why in result.detail

    def test_plain_email_recipient(self, student):
        assertion = _assertion(recipient={"type": "email", "hashed": False, "identity": "Akol@Example.com"})
        with _fetch_returns(assertion):
            assert verify_open_badge(ASSERTION_URL, student.email).status == "verified"

    def test_private_addresses_are_never_fetched(self, student):
        # The real fetcher: the SSRF guard refuses before any request.
        result = verify_open_badge("https://127.0.0.1/assertion", student.email)
        assert result.status == "failed"

    def test_recheck(self, client, student):
        credential = Credential.objects.create(owner=student, provider="open_badge", title="", url=ASSERTION_URL)
        with _fetch_returns(_assertion()):
            res = client.post(f"/api/profile/credentials/{credential.pk}/check/")
        assert res.data["check_status"] == "verified"


@pytest.fixture
def company_owner(db):
    return User.objects.create_user(email="hr@acme.test", name="Acme HR", password="testpass123")


@pytest.fixture
def job(company_owner, category):
    Company.objects.create_with_owner(company_owner, name="Acme Ltd", status="approved", is_verified=True)
    c = APIClient()
    c.force_authenticate(company_owner)
    res = c.post("/api/companies/me/jobs/", {
        "title": "Data Intern", "description": "Help with data.", "category": category.id,
        "application_method": "in_app", "role_type": "internship",
        "requirements": [{"label": "Transcript", "kind": "file", "required": True}],
    }, format="json")
    assert res.status_code == 201, res.data
    return Opportunity.objects.get(pk=res.data["id"])


def _apply(client, job, value):
    req = job.requirements.get()
    return client.post("/api/applications/", {"opportunity": job.pk, "consent": "true", f"answer_{req.pk}": value},
                       format="multipart")


class TestEligibility:
    @pytest.fixture(autouse=True)
    def _gate_on(self, settings):
        settings.REQUIRE_ELIGIBILITY_TO_APPLY = True
        settings.RECENT_GRADUATE_YEARS = 2

    def test_incomplete_profile_cannot_apply(self, client, job):
        res = client.get(f"/api/profile/eligibility/{job.pk}/")
        assert res.data["eligible"] is False and "Finish your profile" in res.data["reasons"][0]
        assert _apply(client, job, SimpleUploadedFile("t.pdf", PDF)).status_code == 400

    def test_student_can_apply(self, client, student, job):
        _complete_profile(student)
        assert client.get(f"/api/profile/eligibility/{job.pk}/").data == {"eligible": True, "reasons": []}
        assert _apply(client, job, SimpleUploadedFile("t.pdf", PDF)).status_code == 201

    def test_recent_graduate_window(self, client, student, job):
        _complete_profile(student, status="graduate", graduation_year=THIS_YEAR - 2)
        assert client.get(f"/api/profile/eligibility/{job.pk}/").data["eligible"] is True
        _complete_profile(student, status="graduate", graduation_year=THIS_YEAR - 3)
        res = client.get(f"/api/profile/eligibility/{job.pk}/")
        assert res.data["eligible"] is False and "last 2 years" in res.data["reasons"][0]
        res = _apply(client, job, SimpleUploadedFile("t.pdf", PDF))
        assert res.status_code == 400 and "last 2 years" in str(res.data)

    def test_role_graduation_range(self, client, student, job):
        job.graduation_year_min, job.graduation_year_max = THIS_YEAR, THIS_YEAR
        job.save()
        _complete_profile(student, graduation_year=THIS_YEAR + 1)
        assert "graduating by" in client.get(f"/api/profile/eligibility/{job.pk}/").data["reasons"][0]

    def test_minors_only_where_accepted(self, client, student, job):
        today = timezone.localdate()
        _complete_profile(student, date_of_birth=date(today.year - 16, 1, 1))
        assert "18 or over" in client.get(f"/api/profile/eligibility/{job.pk}/").data["reasons"][0]
        job.accepts_minors = True
        job.save()
        assert client.get(f"/api/profile/eligibility/{job.pk}/").data["eligible"] is True


class TestApplyingFromTheVault:
    def test_vault_document_is_copied_and_access_is_logged(self, client, student, job, company_owner):
        _complete_profile(student, phone="+211 912 345 678")
        doc_id = _upload(client).data["id"]
        res = _apply(client, job, f"vault:{doc_id}")
        assert res.status_code == 201, res.data
        answer = Application.objects.get().answers.get()
        vault_doc = Document.objects.get()
        assert answer.file.name != vault_doc.file.name and answer.original_filename == "transcript.pdf"

        # Deleting the vault copy leaves the company's copy alone.
        with django_capture_on_commit():
            client.delete(f"/api/profile/documents/{doc_id}/")
        hiring = APIClient()
        hiring.force_authenticate(company_owner)
        download = hiring.get(f"/api/applications/answers/{answer.pk}/file/")
        assert download.status_code == 200 and b"".join(download.streaming_content) == PDF

        log = client.get("/api/profile/access-log/").data
        assert len(log) == 1 and log[0]["company_name"] == "Acme Ltd" and "Transcript" in log[0]["label"]
        # The applicant opening their own file is not logged.
        client.get(f"/api/applications/answers/{answer.pk}/file/")
        assert DocumentAccess.objects.count() == 1

    def test_company_sees_studies_not_birth_date(self, client, student, job, company_owner):
        _complete_profile(student, phone="+211 912 345 678", skills=["Excel"])
        assert _apply(client, job, f"vault:{_upload(client).data['id']}").status_code == 201
        hiring = APIClient()
        hiring.force_authenticate(company_owner)
        listed = hiring.get(f"/api/companies/me/jobs/{job.pk}/applications/").data
        applicant = (listed["results"] if "results" in listed else listed)[0]["applicant"]
        assert applicant["profile"]["institution"] == "University of Juba"
        assert applicant["profile"]["skills"] == ["Excel"]
        assert "date_of_birth" not in applicant["profile"] and applicant["phone"] is None

    def test_someone_elses_document_cannot_be_attached(self, client, job, db):
        other = User.objects.create_user(email="x@x.test", name="X", password="testpass123")
        other_client = APIClient()
        other_client.force_authenticate(other)
        doc_id = _upload(other_client).data["id"]
        res = _apply(client, job, f"vault:{doc_id}")
        assert res.status_code == 400 and "Pick one of your documents" in str(res.data)
