"""Applicant filters, bulk status changes, CSV and printable exports."""

import csv
import io

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Application, Company, ExportLog
from apps.documents.models import Credential
from apps.opportunities.models import Opportunity
from apps.profiles.models import StudentProfile

YEAR = timezone.localdate().year


@pytest.fixture
def hr(db):
    return User.objects.create_user(email="hr@acme.test", name="Acme HR", password="testpass123")


@pytest.fixture
def hr_client(hr):
    c = APIClient()
    c.force_authenticate(hr)
    return c


@pytest.fixture
def job(hr, hr_client, category):
    Company.objects.create_with_owner(hr, name="Acme Ltd", status="approved", is_verified=True)
    res = hr_client.post("/api/companies/me/jobs/", {
        "title": "Data Intern", "description": "Help.", "category": category.id,
        "application_method": "in_app", "role_type": "internship", "requirements": [],
    }, format="json")
    return Opportunity.objects.get(pk=res.data["id"])


def _applicant(job, email, name, *, status="submitted", year=YEAR, institution="University of Juba",
               verified=False, **profile):
    user = User.objects.create_user(email=email, name=name, password="testpass123")
    StudentProfile.objects.create(user=user, institution=institution, programme="BSc Statistics",
                                  graduation_year=year, status="student", phone="+211 900 000 000", **profile)
    if verified:
        Credential.objects.create(owner=user, provider="open_badge", title="Digital Skills",
                                  url="https://b.example/1", check_status="verified")
    return Application.objects.create(opportunity=job, applicant=user, status=status, consent_at=timezone.now())


def _listed(res):
    return res.data["results"] if "results" in res.data else res.data


class TestFilters:
    def test_filters(self, hr_client, job):
        a = _applicant(job, "a@x.test", "Achol", year=YEAR, verified=True)
        b = _applicant(job, "b@x.test", "Bol", year=YEAR + 1, institution="Upper Nile University", status="shortlisted")
        url = f"/api/companies/me/jobs/{job.pk}/applications/"
        ids = lambda **q: {r["id"] for r in _listed(hr_client.get(url, q))}
        assert ids() == {a.pk, b.pk}
        assert ids(status="shortlisted") == {b.pk}
        assert ids(status="submitted,shortlisted") == {a.pk, b.pk}
        assert ids(graduation_year=YEAR + 1) == {b.pk}
        assert ids(verified_certificates="true") == {a.pk}
        assert ids(q="upper nile") == {b.pk}
        assert hr_client.get(url, {"graduation_year": "soon"}).status_code == 400


class TestBulk:
    def test_bulk_shortlist_emails_each_applicant(self, hr_client, job, django_capture_on_commit_callbacks):
        a = _applicant(job, "a@x.test", "Achol")
        b = _applicant(job, "b@x.test", "Bol")
        with django_capture_on_commit_callbacks(execute=True):
            res = hr_client.post(f"/api/companies/me/jobs/{job.pk}/applications/bulk/",
                                 {"ids": [a.pk, b.pk], "status": "shortlisted"}, format="json")
        assert res.status_code == 200 and res.data == {"changed": 2}
        assert set(Application.objects.values_list("status", flat=True)) == {"shortlisted"}
        assert sorted(m.to[0] for m in mail.outbox) == ["a@x.test", "b@x.test"]

    def test_bulk_refuses_other_jobs_and_withdraw(self, hr_client, job, hr, category):
        a = _applicant(job, "a@x.test", "Achol")
        other = Opportunity.objects.create(title="Other", description="x", category=category,
                                           company=job.company, status="approved")
        stray = _applicant(other, "s@x.test", "Stray")
        url = f"/api/companies/me/jobs/{job.pk}/applications/bulk/"
        assert hr_client.post(url, {"ids": [a.pk, stray.pk], "status": "rejected"}, format="json").status_code == 400
        assert hr_client.post(url, {"ids": [a.pk], "status": "withdrawn"}, format="json").status_code == 400
        assert hr_client.post(url, {"ids": [], "status": "rejected"}, format="json").status_code == 400
        a.refresh_from_db()
        assert a.status == "submitted"

    def test_other_company_cannot_bulk(self, job, db):
        a = _applicant(job, "a@x.test", "Achol")
        rival = User.objects.create_user(email="r@r.test", name="R", password="testpass123")
        Company.objects.create_with_owner(rival, name="Rival", status="approved")
        c = APIClient()
        c.force_authenticate(rival)
        res = c.post(f"/api/companies/me/jobs/{job.pk}/applications/bulk/", {"ids": [a.pk], "status": "hired"},
                     format="json")
        assert res.status_code == 404


class TestExports:
    def test_csv_hides_contacts_until_shortlisted_and_is_logged(self, hr_client, job, hr):
        _applicant(job, "a@x.test", "Achol", skills=["Excel"])
        _applicant(job, "b@x.test", "=HYPERLINK(\"http://evil\")", status="shortlisted")
        res = hr_client.get(f"/api/companies/me/jobs/{job.pk}/applications/export.csv")
        assert res.status_code == 200 and res["Content-Type"].startswith("text/csv")
        assert res["Cache-Control"] == "private, no-store"
        rows = list(csv.DictReader(io.StringIO(res.content.decode("utf-8-sig"))))
        by_status = {r["Status"]: r for r in rows}
        assert by_status["Submitted"]["Email"] == "" and by_status["Submitted"]["Skills"] == "Excel"
        assert by_status["Shortlisted"]["Email"] == "b@x.test"
        assert by_status["Shortlisted"]["Name"].startswith("'=")   # no formula injection
        assert "Date of birth" not in rows[0]
        log = ExportLog.objects.get()
        assert log.user == hr and log.row_count == 2 and log.format == "csv"

    def test_filtered_export_and_print(self, hr_client, job):
        _applicant(job, "a@x.test", "Achol <script>")
        _applicant(job, "b@x.test", "Bol", status="rejected")
        res = hr_client.get(f"/api/companies/me/jobs/{job.pk}/applications/print/", {"status": "submitted"})
        html = res.content.decode()
        assert res.status_code == 200 and "Achol &lt;script&gt;" in html and "Bol" not in html
        assert "default-src 'none'" in res["Content-Security-Policy"]
        log = ExportLog.objects.get()
        assert log.format == "print" and log.row_count == 1 and log.filters == {"status": "submitted"}

    def test_needs_two_step_sign_in(self, hr_client, job, settings):
        settings.REQUIRE_MFA_FOR_STAFF_AND_COMPANIES = True
        res = hr_client.get(f"/api/companies/me/jobs/{job.pk}/applications/export.csv")
        assert res.status_code == 403 and not ExportLog.objects.exists()
