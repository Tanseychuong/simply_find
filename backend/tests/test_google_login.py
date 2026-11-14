"""Sign in with Google (apps/accounts/google.py).

Most tests mock ``_decode`` (the signature check) to cover what we do with a
token Google has accepted. ``TestRealTokens`` signs real JWTs with a
throwaway RSA key and runs them through the real verifier, with only the
download of Google's keys replaced."""

import base64
import json
import secrets
import time
from unittest import mock

import pytest
import requests
import rsa
from django.core import mail
from google.auth import crypt, jwt as google_jwt

from apps.accounts.models import User

URL = "/api/auth/google/"
CLIENT_ID = "test-client.apps.googleusercontent.com"
DECODE = "apps.accounts.google._decode"
FETCH = "apps.accounts.google._fetch_certs"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _google_enabled(settings):
    settings.GOOGLE_CLIENT_ID = CLIENT_ID


def claims(sub="g-123", email="ama@gmail.com", **extra):
    now = int(time.time())
    base = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": sub, "email": email,
            "email_verified": True, "name": "Ama Mensah", "iat": now, "exp": now + 3600}
    base.update(extra)
    return base


def unsigned_token(header):
    """A JWT-shaped string with no real signature, built at run time
    (literal tokens in source trip secret scanners)."""
    part = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{part(header)}.{part({})}.{part('x')}"


def throwaway_password():
    return secrets.token_urlsafe(12)


def post(client, token_claims=None, error=None, **body):
    with mock.patch(DECODE, side_effect=error, return_value=token_claims) as decode:
        res = client.post(URL, {"credential": "header.payload.sig", **body}, format="json")
    return res, decode


def me(client, res):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return client.get("/api/auth/me/")


class TestNewAccounts:
    def test_creates_account_without_password_and_signs_in(self, api_client):
        res, _ = post(api_client, claims())
        assert res.status_code == 201 and res.data["created"] is True
        user = User.objects.get(email="ama@gmail.com")
        assert user.google_sub == "g-123" and user.name == "Ama Mensah" and not user.has_usable_password()
        profile = me(api_client, res).data
        assert profile["email"] == "ama@gmail.com" and profile["has_password"] is False and profile["google_linked"]

    def test_second_sign_in_reuses_account(self, api_client):
        post(api_client, claims())
        res, _ = post(api_client, claims())
        assert res.status_code == 200 and res.data["created"] is False and User.objects.count() == 1

    def test_matches_on_google_id_even_if_gmail_address_changed(self, api_client):
        post(api_client, claims())
        res, _ = post(api_client, claims(email="ama.new@gmail.com"))
        assert res.status_code == 200 and User.objects.count() == 1

    def test_name_falls_back_to_email(self, api_client):
        post(api_client, claims(name=""))
        assert User.objects.get().name == "ama"

    def test_new_account_cannot_sign_in_with_any_password(self, api_client):
        post(api_client, claims())
        res = api_client.post("/api/auth/login/", {"email": "ama@gmail.com", "password": ""}, format="json")
        assert res.status_code in (400, 401)


class TestRefused:
    def test_google_unreachable(self, api_client):
        with mock.patch(FETCH, side_effect=requests.ConnectionError("down")):
            res = api_client.post(URL, {"credential": unsigned_token({"alg": "RS256"})}, format="json")
        assert res.status_code == 503 and not User.objects.exists()

    def test_unverified_email(self, api_client):
        res, _ = post(api_client, claims(email_verified=False))
        assert res.status_code == 400 and res.data["code"] == "email_unverified" and not User.objects.exists()

    def test_missing_or_junk_credential(self, api_client):
        assert api_client.post(URL, {}, format="json").status_code == 400
        assert api_client.post(URL, {"credential": "%%%.x.y"}, format="json").status_code == 400

    def test_switched_off_without_client_id(self, api_client, settings):
        settings.GOOGLE_CLIENT_ID = ""
        res, decode = post(api_client, claims())
        assert res.status_code == 503 and res.data["code"] == "google_disabled" and not decode.called

    def test_deactivated_account(self, api_client):
        post(api_client, claims())
        User.objects.update(is_active=False)
        res, _ = post(api_client, claims())
        assert res.status_code == 401 and "access" not in res.data


class TestRealTokens:
    """The real verifier, with a key pair we control standing in for Google's."""

    @pytest.fixture(autouse=True)
    def keys(self):
        public, private = rsa.newkeys(1024)
        other_public, other_private = rsa.newkeys(1024)
        self.signer = crypt.RSASigner.from_string(private.save_pkcs1(), "k1")
        self.impostor = crypt.RSASigner.from_string(other_private.save_pkcs1(), "k1")
        self.certs = {"k1": public.save_pkcs1().decode()}

    def token(self, signer=None, **overrides):
        return google_jwt.encode(signer or self.signer, claims(**overrides)).decode()

    def send(self, client, credential):
        with mock.patch(FETCH, return_value=(self.certs, 3600)) as fetch:
            res = client.post(URL, {"credential": credential}, format="json")
        return res, fetch

    def test_valid_token_signs_in(self, api_client):
        res, _ = self.send(api_client, self.token())
        assert res.status_code == 201

    @pytest.mark.parametrize("overrides", [
        {"aud": "someone-elses-client.apps.googleusercontent.com"},
        {"iat": 1, "exp": 2},  # expired
        {"iss": "https://evil.example"},  # a GoogleAuthError, not a ValueError, inside google-auth
    ], ids=["wrong-audience", "expired", "wrong-issuer"])
    def test_rejected_with_400_not_503(self, api_client, overrides):
        res, _ = self.send(api_client, self.token(**overrides))
        assert res.status_code == 400 and not User.objects.exists()

    def test_signed_by_another_key(self, api_client):
        res, _ = self.send(api_client, self.token(signer=self.impostor))
        assert res.status_code == 400 and not User.objects.exists()

    def test_keys_are_cached_between_sign_ins(self, api_client):
        with mock.patch(FETCH, return_value=(self.certs, 3600)) as fetch:
            for _ in range(3):
                api_client.post(URL, {"credential": self.token()}, format="json")
        assert fetch.call_count == 1

    def test_unknown_key_id_refetches_at_most_once_a_minute(self, api_client):
        stranger = crypt.RSASigner.from_string(rsa.newkeys(1024)[1].save_pkcs1(), "k9")
        with mock.patch(FETCH, return_value=(self.certs, 3600)) as fetch:
            for _ in range(4):
                res = api_client.post(URL, {"credential": self.token(signer=stranger)}, format="json")
                assert res.status_code == 400
        assert fetch.call_count == 2  # first load + one refetch for the unknown key


class TestExistingAccounts:
    """Registration doesn't verify email, so a password account is only
    linked once its password is entered too."""

    def test_asks_for_password_instead_of_signing_in(self, api_client, user):
        res, _ = post(api_client, claims(email=user.email))
        user.refresh_from_db()
        assert res.status_code == 409 and res.data["code"] == "link_required" and res.data["email"] == user.email
        assert "access" not in res.data and user.google_sub is None

    def test_wrong_password_does_not_link(self, api_client, user):
        res, _ = post(api_client, claims(email=user.email), password="wrong")
        user.refresh_from_db()
        assert res.status_code == 400 and res.data["code"] == "link_password_wrong" and user.google_sub is None

    def test_right_password_links_and_signs_in(self, api_client, user):
        res, _ = post(api_client, claims(email=user.email.upper()), password="testpass123")
        user.refresh_from_db()
        assert res.status_code == 200 and user.google_sub == "g-123" and user.has_usable_password()
        assert me(api_client, res).data["id"] == user.id
        # From then on Google alone is enough.
        api_client.credentials()
        res, _ = post(api_client, claims(email=user.email))
        assert res.status_code == 200

    def test_email_linked_to_another_google_account(self, api_client, user):
        User.objects.filter(pk=user.pk).update(google_sub="someone-else")
        res, _ = post(api_client, claims(email=user.email), password="testpass123")
        assert res.status_code == 409 and res.data["code"] == "other_google_account" and "access" not in res.data

    def test_passwordless_staff_account_is_never_claimed_by_email(self, api_client):
        admin = User.objects.create_superuser(email="admin@example.com", name="Admin", password=None)
        res, _ = post(api_client, claims(email="admin@example.com"))
        admin.refresh_from_db()
        assert res.status_code == 403 and "access" not in res.data and admin.google_sub is None

    def test_case_variant_duplicates_are_refused_not_guessed(self, api_client):
        first = throwaway_password()
        User.objects.create_user(email="Ama@gmail.com", name="A", password=first)
        User.objects.create_user(email="AMA@gmail.com", name="B", password=throwaway_password())
        res, _ = post(api_client, claims(email="ama@gmail.com"), password=first)
        assert res.status_code == 409 and res.data["code"] == "ambiguous_email"
        assert not User.objects.exclude(google_sub=None).exists()


class TestRecovery:
    def test_google_only_account_can_set_a_password_by_reset(self, api_client):
        post(api_client, claims())
        res = api_client.post("/api/auth/password-reset/", {"email": "ama@gmail.com"}, format="json")
        assert res.status_code == 200 and len(mail.outbox) == 1 and "reset-password" in mail.outbox[0].body

    def test_registration_rejects_a_case_variant_of_an_existing_email(self, api_client, user):
        res = api_client.post("/api/auth/register/", {"name": "X", "email": user.email.upper(),
                                                      "password": throwaway_password()}, format="json")
        assert res.status_code == 400 and "email" in res.data and User.objects.count() == 1


class TestDeletingAGoogleAccount:
    URL = "/api/auth/me/delete/"

    def _google_user(self, api_client):
        post(api_client, claims())
        user = User.objects.get()
        api_client.force_authenticate(user)
        return user

    def _delete(self, api_client, token_claims):
        with mock.patch(DECODE, return_value=token_claims):
            return api_client.post(self.URL, {"google_credential": "x.y.z"}, format="json")

    def test_confirmed_with_same_google_account(self, api_client):
        user = self._google_user(api_client)
        res = self._delete(api_client, claims())
        user.refresh_from_db()
        assert res.status_code == 200 and not user.is_active

    def test_other_google_account_refused(self, api_client):
        user = self._google_user(api_client)
        res = self._delete(api_client, claims(sub="intruder"))
        user.refresh_from_db()
        assert res.status_code == 400 and user.is_active

    def test_old_google_token_refused(self, api_client):
        user = self._google_user(api_client)
        res = self._delete(api_client, claims(iat=int(time.time()) - 600))
        user.refresh_from_db()
        assert res.status_code == 400 and user.is_active

    def test_empty_password_does_not_pass_for_passwordless_account(self, api_client):
        user = self._google_user(api_client)
        res = api_client.post(self.URL, {"password": ""}, format="json")
        user.refresh_from_db()
        assert res.status_code == 400 and user.is_active

    def test_password_accounts_still_need_the_password(self, api_client, user):
        User.objects.filter(pk=user.pk).update(google_sub="g-123")
        api_client.force_authenticate(user)
        res = self._delete(api_client, claims())
        user.refresh_from_db()
        assert res.status_code == 400 and user.is_active
