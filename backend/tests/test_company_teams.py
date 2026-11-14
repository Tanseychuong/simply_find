"""Company accounts managed by a team: roles, invitations, and what happens
to a shared company when one person leaves or deletes their account."""

import re
import secrets
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.deletion import DELETION_HOLD
from apps.accounts.models import User
from apps.companies.models import Company, CompanyInvitation, CompanyMembership
from apps.opportunities.models import Opportunity

pytestmark = pytest.mark.django_db
# Generated at run time: literal passwords in source trip secret scanners.
PASSWORD = secrets.token_urlsafe(12)
TEAM = "/api/companies/me/team/"


@pytest.fixture(autouse=True)
def _send_emails_now(monkeypatch):
    # Emails go out after the commit; tests run inside one transaction.
    monkeypatch.setattr("apps.companies.notifications.transaction.on_commit", lambda fn, *a, **k: fn())


@pytest.fixture(autouse=True)
def _local(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    fs = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    settings.STORAGES = {**settings.STORAGES, "default": fs, "applications": fs}


def person(email, name=None):
    user = User.objects.create_user(email=email, name=name or email.split("@")[0], password=PASSWORD)
    client = APIClient()
    client.force_authenticate(user)
    return user, client


def join(company, user, role):
    return CompanyMembership.objects.create(company=company, user=user, role=role)


@pytest.fixture
def team():
    """Acme, approved, with an owner, an admin and a recruiter."""
    owner, owner_c = person("owner@acme.test", "Olu Owner")
    company = Company.objects.create_with_owner(owner, name="Acme", status="approved", contact_email="jobs@acme.test")
    admin, admin_c = person("admin@acme.test", "Ada Admin")
    recruiter, rec_c = person("rec@acme.test", "Rex Recruiter")
    join(company, admin, "admin")
    join(company, recruiter, "recruiter")
    return {"company": company, "owner": (owner, owner_c), "admin": (admin, admin_c), "recruiter": (recruiter, rec_c)}


def invite(client, email, role="recruiter"):
    return client.post(f"{TEAM}invitations/", {"email": email, "role": role}, format="json")


def token_from_email():
    match = re.search(r"/companies/invite/([\w-]+)", mail.outbox[-1].body)
    return match.group(1)


class TestCompanyIsItsOwnAccount:
    def test_signing_up_makes_you_its_first_owner(self, category):
        user, client = person("founder@new.test")
        res = client.post("/api/companies/", {"name": "NewCo", "accept_terms": True}, format="json")
        company = Company.objects.get()
        assert res.status_code == 201 and res.data["my_role"] == "owner"
        assert company.created_by == user and company.memberships.get().role == "owner"
        assert client.get("/api/auth/me/").data["company"]["role"] == "owner"

    def test_one_company_per_person(self, team):
        _, owner_c = team["owner"]
        res = owner_c.post("/api/companies/", {"name": "Second", "accept_terms": True}, format="json")
        assert res.status_code == 400 and Company.objects.count() == 1

    def test_every_member_sees_the_team(self, team):
        _, rec_c = team["recruiter"]
        data = rec_c.get(TEAM).data
        assert data["my_role"] == "recruiter" and len(data["members"]) == 3
        assert data["invitations"] == []  # only owners/admins see open invitations


class TestRoles:
    def test_recruiter_works_on_jobs_but_not_the_profile(self, team, category):
        _, rec_c = team["recruiter"]
        job = rec_c.post("/api/companies/me/jobs/", {"title": "Analyst", "description": "x", "category": category.id,
                                                      "opportunity_url": "https://acme.test/jobs/1"}, format="json")
        assert job.status_code == 201
        assert rec_c.patch("/api/companies/me/", {"description": "hacked"}, format="json").status_code == 403
        logo = SimpleUploadedFile("l.png", b"\x89PNG\r\n", content_type="image/png")
        assert rec_c.post("/api/companies/me/logo/", {"logo": logo}, format="multipart").status_code == 403

    def test_admin_edits_the_profile(self, team):
        _, admin_c = team["admin"]
        res = admin_c.patch("/api/companies/me/", {"description": "We build things."}, format="json")
        assert res.status_code == 200 and res.data["description"] == "We build things."

    def test_only_owners_change_roles(self, team):
        rec = team["recruiter"][0].company_membership
        _, admin_c = team["admin"]
        assert admin_c.patch(f"{TEAM}members/{rec.pk}/", {"role": "admin"}, format="json").status_code == 403
        _, owner_c = team["owner"]
        res = owner_c.patch(f"{TEAM}members/{rec.pk}/", {"role": "admin"}, format="json")
        assert res.status_code == 200 and res.data["role"] == "admin"

    def test_last_owner_cannot_step_down_or_leave(self, team):
        owner, owner_c = team["owner"]
        me = owner.company_membership
        assert owner_c.patch(f"{TEAM}members/{me.pk}/", {"role": "admin"}, format="json").status_code == 400
        assert owner_c.delete(f"{TEAM}members/{me.pk}/").status_code == 400
        # With a second owner, they can.
        CompanyMembership.objects.filter(user=team["admin"][0]).update(role="owner")
        assert owner_c.delete(f"{TEAM}members/{me.pk}/").status_code == 204

    def test_who_can_remove_whom(self, team):
        _, admin_c = team["admin"]
        _, rec_c = team["recruiter"]
        owner_m = team["owner"][0].company_membership
        admin_m = team["admin"][0].company_membership
        rec_m = team["recruiter"][0].company_membership
        assert rec_c.delete(f"{TEAM}members/{admin_m.pk}/").status_code == 403
        assert admin_c.delete(f"{TEAM}members/{owner_m.pk}/").status_code == 403
        assert admin_c.delete(f"{TEAM}members/{rec_m.pk}/").status_code == 204
        assert admin_c.delete(f"{TEAM}members/{admin_m.pk}/").status_code == 204  # leaving
        assert team["company"].memberships.count() == 1

    def test_cannot_act_on_another_companys_members(self, team):
        stranger, stranger_c = person("boss@other.test")
        Company.objects.create_with_owner(stranger, name="Other", status="approved")
        rec_m = team["recruiter"][0].company_membership
        assert stranger_c.delete(f"{TEAM}members/{rec_m.pk}/").status_code == 404

    def test_removed_member_loses_access(self, team):
        rec, rec_c = team["recruiter"]
        rec.company_membership.delete()
        assert rec_c.get("/api/companies/me/jobs/").status_code == 404


class TestInvitations:
    def test_owner_invites_and_the_invitee_joins(self, team):
        _, owner_c = team["owner"]
        res = invite(owner_c, "New.Hire@Acme.test", "admin")
        assert res.status_code == 201
        assert mail.outbox[-1].to == ["New.Hire@Acme.test"] and "Acme" in mail.outbox[-1].subject
        token = token_from_email()
        # Only a hash is stored.
        assert not CompanyInvitation.objects.filter(token_hash=token).exists()

        anon = APIClient().get(f"/api/companies/invitations/{token}/")
        assert anon.status_code == 200 and anon.data["company"]["name"] == "Acme" and anon.data["role"] == "admin"

        newbie, newbie_c = person("new.hire@acme.test")
        res = newbie_c.post(f"/api/companies/invitations/{token}/", format="json")
        assert res.status_code == 200 and res.data["my_role"] == "admin"
        assert newbie.company_membership.company == team["company"]
        # Single use.
        assert newbie_c.post(f"/api/companies/invitations/{token}/", format="json").status_code == 400

    def test_must_accept_with_the_invited_address(self, team):
        invite(team["owner"][1], "right@person.test")
        _, wrong_c = person("forwarded@person.test")
        res = wrong_c.post(f"/api/companies/invitations/{token_from_email()}/", format="json")
        assert res.status_code == 403 and not CompanyMembership.objects.filter(user__email="forwarded@person.test").exists()

    def test_expired_invitation(self, team):
        invite(team["owner"][1], "late@person.test")
        CompanyInvitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        _, late_c = person("late@person.test")
        assert late_c.post(f"/api/companies/invitations/{token_from_email()}/", format="json").status_code == 400

    def test_someone_on_another_team_cannot_join(self, team):
        invite(team["owner"][1], "busy@other.test")
        busy, busy_c = person("busy@other.test")
        Company.objects.create_with_owner(busy, name="Other")
        assert busy_c.post(f"/api/companies/invitations/{token_from_email()}/", format="json").status_code == 400

    def test_bad_token(self):
        assert APIClient().get("/api/companies/invitations/not-a-real-token/").status_code == 404

    def test_who_may_invite(self, team):
        assert invite(team["recruiter"][1], "x@y.test").status_code == 403
        assert invite(team["admin"][1], "x@y.test", "owner").status_code == 403
        assert invite(team["admin"][1], "x@y.test", "admin").status_code == 201

    def test_cannot_invite_an_existing_member(self, team):
        assert invite(team["owner"][1], "REC@acme.test").status_code == 400

    def test_reinviting_replaces_the_old_link(self, team):
        invite(team["owner"][1], "again@person.test")
        first = token_from_email()
        invite(team["owner"][1], "again@person.test")
        assert CompanyInvitation.objects.count() == 1
        assert APIClient().get(f"/api/companies/invitations/{first}/").status_code == 404

    def test_revoking(self, team):
        _, owner_c = team["owner"]
        invitation_id = invite(owner_c, "maybe@person.test").data["id"]
        token = token_from_email()
        assert owner_c.delete(f"{TEAM}invitations/{invitation_id}/").status_code == 204
        _, maybe_c = person("maybe@person.test")
        assert maybe_c.post(f"/api/companies/invitations/{token}/", format="json").status_code == 404


class TestTeamAndApplicants:
    @pytest.fixture
    def application(self, team, category):
        owner = team["owner"][0]
        job = Opportunity.objects.create(title="Job", description="x", category=category, company=team["company"],
                                         posted_by=owner, application_method="in_app")
        job.approve(owner)
        req = job.requirements.create(label="CV", kind="file")
        _, applicant_c = person("applicant@mail.test")
        applicant_c.post("/api/applications/", {"opportunity": job.pk, "consent": "true",
                                                f"answer_{req.pk}": SimpleUploadedFile("cv.pdf", b"%PDF")},
                         format="multipart")
        return job

    def test_every_member_can_read_applicants_and_cvs(self, team, application):
        from apps.companies.models import ApplicationAnswer
        answer = ApplicationAnswer.objects.get()
        for key in ("owner", "admin", "recruiter"):
            _, client = team[key]
            assert client.get(f"/api/companies/me/jobs/{application.pk}/applications/").status_code == 200
            assert client.get(f"/api/applications/answers/{answer.pk}/file/").status_code == 200

    def test_former_member_cannot_download_cvs(self, team, application):
        from apps.companies.models import ApplicationAnswer
        answer = ApplicationAnswer.objects.get()
        rec, rec_c = team["recruiter"]
        rec.company_membership.delete()
        assert rec_c.get(f"/api/applications/answers/{answer.pk}/file/").status_code == 404

    def test_team_members_cannot_apply_to_their_own_jobs(self, team, application):
        _, rec_c = team["recruiter"]
        res = rec_c.post("/api/applications/", {"opportunity": application.pk, "consent": "true"}, format="multipart")
        assert res.status_code == 400

    def test_new_application_emails_owners_admins_and_contact_not_recruiters(self, team, application):
        notice = next(m for m in mail.outbox if m.subject.startswith("New application"))
        assert sorted(notice.to) == ["admin@acme.test", "jobs@acme.test", "owner@acme.test"]


class TestModeration:
    def test_review_shows_who_signed_up_and_team_size(self, team, moderator_user):
        client = APIClient()
        client.force_authenticate(moderator_user)
        row = client.get("/api/companies/review/?status=approved").data
        row = row["results"][0] if isinstance(row, dict) else row[0]
        assert row["created_by_email"] == "owner@acme.test" and row["member_count"] == 3


class TestDeletingAnAccount:
    def _delete_and_purge(self, client, user):
        client.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        User.objects.filter(pk=user.pk).update(deletion_requested_at=timezone.now() - DELETION_HOLD - timedelta(minutes=1))
        call_command("purge_deleted_accounts")

    def test_sole_owner_hands_over_to_an_admin(self, team, category, django_capture_on_commit_callbacks):
        owner, owner_c = team["owner"]
        job = Opportunity.objects.create(title="Job", description="x", category=category, company=team["company"],
                                         posted_by=owner)
        with django_capture_on_commit_callbacks(execute=True):
            owner_c.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        admin = team["admin"][0]
        assert CompanyMembership.objects.get(user=admin).role == "owner"
        assert any(m.to == [admin.email] and "now an owner" in m.subject for m in mail.outbox)
        team["company"].refresh_from_db()
        assert team["company"].status == "approved"  # the company carries on

        self._delete_and_purge(APIClient(), owner)
        job.refresh_from_db()
        assert Company.objects.filter(pk=team["company"].pk).exists()
        assert job.posted_by == admin  # the job stays with the company

    def test_recruiter_is_promoted_when_no_admin_is_left(self, team):
        CompanyMembership.objects.filter(user=team["admin"][0]).delete()
        owner, owner_c = team["owner"]
        owner_c.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        assert CompanyMembership.objects.get(user=team["recruiter"][0]).role == "owner"

    def test_only_member_company_is_suspended_then_deleted(self, category):
        solo, solo_c = person("solo@shop.test")
        company = Company.objects.create_with_owner(solo, name="Solo", status="approved", is_verified=True)
        job = Opportunity.objects.create(title="Job", description="x", category=category, company=company, posted_by=solo)
        solo_c.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        company.refresh_from_db()
        assert company.status == "suspended"
        self._delete_and_purge(solo_c, solo)
        assert not Company.objects.filter(pk=company.pk).exists() and not Opportunity.objects.filter(pk=job.pk).exists()


class TestReviewFixes:
    """Regression tests for the /code-review findings on company teams."""

    def _job(self, company, poster, category, status="approve"):
        job = Opportunity.objects.create(title="Job", description="x", category=category, company=company,
                                         posted_by=poster, application_method="in_app")
        if status == "approve":
            job.approve(poster)
        return job

    def test_applicant_downloads_own_cv_when_company_has_a_team(self, team, category):
        from apps.companies.models import ApplicationAnswer
        job = self._job(team["company"], team["owner"][0], category)
        req = job.requirements.create(label="CV", kind="file")
        _, applicant_c = person("applicant@mail.test")
        applicant_c.post("/api/applications/", {"opportunity": job.pk, "consent": "true",
                                                f"answer_{req.pk}": SimpleUploadedFile("cv.pdf", b"%PDF")},
                         format="multipart")
        answer = ApplicationAnswer.objects.get()
        assert applicant_c.get(f"/api/applications/answers/{answer.pk}/file/").status_code == 200

    def test_removed_members_jobs_stay_and_survive_their_account_deletion(self, team, category):
        rec, _ = team["recruiter"]
        job = self._job(team["company"], rec, category)
        team["owner"][1].delete(f"{TEAM}members/{CompanyMembership.objects.get(user=rec).pk}/")
        job.refresh_from_db()
        assert job.posted_by == team["owner"][0]
        rec.delete()
        assert Opportunity.objects.filter(pk=job.pk).exists()

    def test_deleting_a_member_in_django_admin_keeps_company_jobs(self, team, category, admin_user):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        rec, _ = team["recruiter"]
        job = self._job(team["company"], rec, category)
        request = RequestFactory().post("/")
        request.user = admin_user
        site._registry[User].delete_model(request, rec)
        assert Opportunity.objects.get(pk=job.pk).posted_by == team["owner"][0]

    def test_removed_member_cannot_read_unpublished_job_they_posted(self, team, category):
        rec, rec_c = team["recruiter"]
        job = self._job(team["company"], rec, category, status="pending")
        CompanyMembership.objects.filter(user=rec).delete()  # removed without the service (worst case)
        assert rec_c.get(f"/api/opportunities/{job.pk}/").status_code == 404

    def test_owner_awaiting_deletion_does_not_count_as_an_owner(self, team):
        CompanyMembership.objects.filter(user=team["admin"][0]).update(role="owner")
        owner, owner_c = team["owner"]
        owner_c.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        admin, admin_c = team["admin"]
        me = CompanyMembership.objects.get(user=admin)
        assert admin_c.patch(f"{TEAM}members/{me.pk}/", {"role": "recruiter"}, format="json").status_code == 400
        assert admin_c.delete(f"{TEAM}members/{me.pk}/").status_code == 400

    def test_non_owner_leaving_still_leaves_an_active_owner(self, team):
        User.objects.filter(pk=team["owner"][0].pk).update(is_active=False)  # owner already pending deletion
        rec, rec_c = team["recruiter"]
        rec_c.post("/api/auth/me/delete/", {"password": PASSWORD}, format="json")
        assert CompanyMembership.objects.get(user=team["admin"][0]).role == "owner"

    def test_expired_invitations_do_not_block_new_ones(self, team):
        owner = team["owner"][0]
        for i in range(50):
            CompanyInvitation.issue(team["company"], f"old{i}@x.test", "recruiter", owner)
        CompanyInvitation.objects.update(expires_at=timezone.now() - timedelta(days=1))
        assert invite(team["owner"][1], "fresh@x.test").status_code == 201

    def test_accepting_two_invitations_at_once_is_a_clear_error(self, team):
        from unittest import mock
        invite(team["owner"][1], "double@x.test")
        token = token_from_email()
        user, client = person("double@x.test")
        other = Company.objects.create(name="Other", created_by=user)
        CompanyMembership.objects.create(company=other, user=user, role="owner")
        real = CompanyMembership.for_user
        # The other acceptance commits between our check and our insert.
        with mock.patch.object(CompanyMembership, "for_user", side_effect=[None, real(user)]):
            res = client.post(f"/api/companies/invitations/{token}/", format="json")
        assert res.status_code == 400 and "Other" in str(res.data)

    def test_permissions_are_sent_to_the_frontend(self, team):
        assert team["recruiter"][1].get(TEAM).data["my_permissions"]["invite"] is False
        perms = team["owner"][1].get("/api/companies/me/").data["my_permissions"]
        assert perms["change_roles"] and perms["invite_owners"]
