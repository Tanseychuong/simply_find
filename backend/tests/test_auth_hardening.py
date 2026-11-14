"""Email verification, cookie sessions with CSRF, refresh rotation, sign-out,
two-step sign-in for staff and company teams, and hidden applicant contacts."""

import pyotp
import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import mfa, verification
from apps.accounts.models import User
from apps.companies.models import Company

pytestmark = pytest.mark.django_db
PASSWORD = "testpass123"


@pytest.fixture
def gates_on(settings):
    settings.REQUIRE_VERIFIED_EMAIL = True
    settings.REQUIRE_MFA_FOR_STAFF_AND_COMPANIES = True


@pytest.fixture
def send_now(monkeypatch):
    monkeypatch.setattr("apps.accounts.verification.transaction.on_commit", lambda fn, *a, **k: fn())


def _login(client, user, password=PASSWORD):
    return client.post("/api/auth/login/", {"email": user.email, "password": password}, format="json")


def _code(user):
    return pyotp.TOTP(mfa.decrypt(User.objects.get(pk=user.pk).mfa_secret)).now()


def _fresh_code(user):
    """A code for the next sign-in. Codes work once, and tests run within
    one 30-second step, so forget the step the last code used."""
    User.objects.filter(pk=user.pk).update(mfa_last_step=None)
    return _code(user)


def _turn_on_mfa(user):
    mfa.start_setup(user)
    return mfa.enable(user, _code(user))


class TestEmailVerification:
    def test_register_sends_a_link_that_confirms(self, api_client, send_now):
        res = api_client.post("/api/auth/register/", {"name": "Ada", "email": "ada@uni.test", "password": "Str0ng-pass!"})
        assert res.status_code == 201 and res.data["user"]["email_verified"] is False
        assert len(mail.outbox) == 1 and "/verify-email?token=" in mail.outbox[0].body
        token = mail.outbox[0].body.split("token=")[1].split()[0]

        assert APIClient().post("/api/auth/verify-email/", {"token": token}).status_code == 200
        assert User.objects.get(email="ada@uni.test").email_verified

    def test_bad_link_refused(self, api_client):
        assert api_client.post("/api/auth/verify-email/", {"token": "nope"}).status_code == 400

    def test_link_dies_when_the_email_changes(self, api_client, user):
        token = verification.make_token(user)
        User.objects.filter(pk=user.pk).update(email="other@example.com")
        assert api_client.post("/api/auth/verify-email/", {"token": token}).status_code == 400

    def test_resend(self, api_client, user, send_now):
        api_client.force_authenticate(user)
        assert api_client.post("/api/auth/verify-email/resend/").status_code == 200
        assert len(mail.outbox) == 1

    def test_applying_waits_for_a_confirmed_email(self, api_client, user, gates_on):
        api_client.force_authenticate(user)
        res = api_client.post("/api/applications/", {"opportunity": 1}, format="multipart")
        assert res.status_code == 403 and res.data["code"] == "email_not_verified"

    def test_creating_a_company_waits_for_a_confirmed_email(self, api_client, user, gates_on):
        api_client.force_authenticate(user)
        res = api_client.post("/api/companies/", {"name": "Acme", "accept_terms": True}, format="json")
        assert res.status_code == 403 and res.data["code"] == "email_not_verified"
        verification.mark_verified(user)
        assert api_client.post("/api/companies/", {"name": "Acme", "accept_terms": True},
                               format="json").status_code == 201

    def test_password_reset_confirms_the_email(self, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        APIClient().post("/api/auth/password-reset/confirm/", {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user), "password": "N3w-Passw0rd!x",
        }, format="json")
        assert User.objects.get(pk=user.pk).email_verified

    def test_short_passwords_refused(self, api_client):
        res = api_client.post("/api/auth/register/", {"name": "A", "email": "a@b.test", "password": "Abc!2345x"})
        assert res.status_code == 400 and "password" in res.data


class TestCookieSessions:
    def test_cookie_signs_in_and_unsafe_requests_need_csrf(self, user):
        client = APIClient(enforce_csrf_checks=True)
        assert _login(client, user).status_code == 200
        assert client.get("/api/auth/me/").data["email"] == user.email

        assert client.patch("/api/auth/me/", {"name": "New"}, format="json").status_code == 403  # no CSRF token
        csrf = client.get("/api/auth/csrf/").data["csrfToken"]
        res = client.patch("/api/auth/me/", {"name": "New"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        assert res.status_code == 200 and res.data["name"] == "New"

    def test_bearer_header_still_works_without_csrf(self, user):
        token = _login(APIClient(), user).cookies["sf_access"].value
        client = APIClient(enforce_csrf_checks=True)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert client.patch("/api/auth/me/", {"name": "Via header"}, format="json").status_code == 200

    def test_refresh_rotates_and_the_old_token_dies(self, user):
        client = APIClient()
        old = _login(client, user).cookies["sf_refresh"].value
        res = client.post("/api/auth/refresh/")
        assert res.status_code == 200 and res.cookies["sf_refresh"].value != old
        assert APIClient().post("/api/auth/refresh/", {"refresh": old}, format="json").status_code == 401

    def test_logout_revokes_and_clears(self, user):
        client = APIClient()
        refresh = _login(client, user).cookies["sf_refresh"].value
        res = client.post("/api/auth/logout/")
        assert res.cookies["sf_access"].value == "" and res.cookies["sf_refresh"].value == ""
        assert APIClient().post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code == 401

    def test_login_is_case_insensitive_and_gives_one_answer_for_wrong_details(self, api_client, user):
        assert _login(api_client, User(email=user.email.upper())).status_code == 200
        wrong = _login(api_client, user, password="nope-nope-nope")
        missing = _login(api_client, User(email="nobody@example.com"))
        assert wrong.status_code == missing.status_code == 401 and wrong.data == missing.data


class TestTwoStepSignIn:
    def test_setup_enable_and_sign_in_with_a_code(self, user):
        client = APIClient()
        _login(client, user)
        setup = client.post("/api/auth/mfa/setup/", {"password": PASSWORD}, format="json")
        assert setup.status_code == 200 and setup.data["otpauth_uri"].startswith("otpauth://totp/SimplyFind:")
        assert client.post("/api/auth/mfa/enable/", {"code": "000000"}, format="json").status_code == 400
        enabled = client.post("/api/auth/mfa/enable/", {"code": _code(user)}, format="json")
        assert enabled.status_code == 200 and len(enabled.data["recovery_codes"]) == 10

        step1 = _login(APIClient(), user)
        assert step1.data["mfa_required"] is True and "sf_access" not in step1.cookies
        fresh = APIClient()
        res = fresh.post("/api/auth/mfa/login/", {"mfa_token": step1.data["mfa_token"], "code": _fresh_code(user)},
                         format="json")
        assert res.status_code == 200 and "sf_access" in res.cookies

    def test_secret_is_stored_encrypted(self, user):
        setup = mfa.start_setup(user)
        stored = User.objects.get(pk=user.pk).mfa_secret
        assert setup["secret"] not in stored and mfa.decrypt(stored) == setup["secret"]

    def test_a_code_works_once(self, user):
        mfa.start_setup(user)
        code = _code(user)
        assert mfa.enable(user, code) is not None
        assert mfa.verify(User.objects.get(pk=user.pk), code) is False

    def test_recovery_code_works_once(self, user):
        codes = _turn_on_mfa(user)
        user = User.objects.get(pk=user.pk)
        assert mfa.verify(user, codes[0]) is True
        assert mfa.verify(User.objects.get(pk=user.pk), codes[0]) is False

    def test_wrong_password_cannot_start_setup(self, api_client, user):
        api_client.force_authenticate(user)
        assert api_client.post("/api/auth/mfa/setup/", {"password": "wrong"}, format="json").status_code == 400

    def test_challenge_dies_when_the_password_changes(self, user):
        _turn_on_mfa(user)
        token = _login(APIClient(), user).data["mfa_token"]
        user = User.objects.get(pk=user.pk)
        user.set_password("An0ther-passw0rd")
        user.save()
        res = APIClient().post("/api/auth/mfa/login/", {"mfa_token": token, "code": _fresh_code(user)}, format="json")
        assert res.status_code == 401

    def test_disable_needs_password_and_code(self, user):
        _turn_on_mfa(user)
        client = APIClient()
        token = _login(client, user).data["mfa_token"]
        assert client.post("/api/auth/mfa/login/", {"mfa_token": token, "code": _fresh_code(user)},
                           format="json").status_code == 200
        assert client.post("/api/auth/mfa/disable/", {"password": PASSWORD}, format="json").status_code == 400
        assert client.post("/api/auth/mfa/disable/", {"password": PASSWORD, "code": _fresh_code(user)},
                           format="json").status_code == 200
        assert not User.objects.get(pk=user.pk).mfa_enabled


class TestTwoStepRequiredForCompaniesAndStaff:
    @pytest.fixture
    def company_user(self, db):
        owner = User.objects.create_user(email="hr@acme.test", name="HR", password=PASSWORD)
        Company.objects.create_with_owner(owner, name="Acme", status=Company.Status.APPROVED)
        return owner

    def test_company_tools_need_setup_then_a_two_step_session(self, company_user, gates_on):
        client = APIClient()
        _login(client, company_user)
        res = client.get("/api/companies/me/")
        assert res.status_code == 403 and res.data["code"] == "mfa_setup_required"
        assert client.get("/api/auth/me/").data["mfa_required"] is True

        _turn_on_mfa(company_user)
        password_only = APIClient()
        assert "sf_access" not in _login(password_only, company_user).cookies  # asked for the code instead

        token = _login(APIClient(), company_user).data["mfa_token"]
        full = APIClient()
        full.post("/api/auth/mfa/login/", {"mfa_token": token, "code": _fresh_code(company_user)}, format="json")
        assert full.get("/api/companies/me/").status_code == 200

    def test_a_session_from_before_mfa_was_turned_on_is_not_enough(self, company_user, gates_on):
        client = APIClient()
        _login(client, company_user)
        _turn_on_mfa(company_user)
        res = client.get("/api/companies/me/jobs/")
        assert res.status_code == 403 and res.data["code"] == "mfa_required"

    def test_moderation_needs_two_step(self, moderator_user, gates_on):
        moderator_user.set_password(PASSWORD)
        moderator_user.save()
        client = APIClient()
        _login(client, moderator_user)
        res = client.get("/api/opportunities/pending/")
        assert res.status_code == 403 and res.data["code"] == "mfa_setup_required"

    def test_students_are_not_asked(self, user, gates_on):
        client = APIClient()
        assert "sf_access" in _login(client, user).cookies
        assert client.get("/api/auth/me/").data["mfa_required"] is False

    def test_admin_login_needs_a_code(self, admin_user, gates_on):
        url = reverse("admin:login")
        client = APIClient()
        res = client.post(url, {"username": admin_user.email, "password": PASSWORD, "next": "/admin/"})
        assert res.status_code == 200 and b"Set up two-step sign-in" in res.content

        _turn_on_mfa(admin_user)
        res = client.post(url, {"username": admin_user.email, "password": PASSWORD, "otp": "000000", "next": "/admin/"})
        assert res.status_code == 200  # form shown again
        res = client.post(url, {"username": admin_user.email, "password": PASSWORD, "otp": _fresh_code(admin_user),
                                "next": "/admin/"})
        assert res.status_code == 302


def test_setup_mfa_command(user, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    real_start = mfa.start_setup
    made = {}

    def start_and_remember(u):
        made.update(real_start(u))
        return made

    monkeypatch.setattr("apps.accounts.management.commands.setup_mfa.mfa.start_setup", start_and_remember)
    monkeypatch.setattr("builtins.input", lambda prompt="": pyotp.TOTP(made["secret"]).now())
    out = StringIO()
    call_command("setup_mfa", user.email, stdout=out)
    assert "Recovery codes" in out.getvalue() and User.objects.get(pk=user.pk).mfa_enabled
