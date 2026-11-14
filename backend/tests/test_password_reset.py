import re

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

REQUEST_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"


def _uid_token(user):
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_sends_email_with_reset_link(self, api_client, user, settings):
        settings.FRONTEND_URL = "https://simplyfind.example"
        response = api_client.post(REQUEST_URL, {"email": user.email})
        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert "https://simplyfind.example/reset-password?uid=" in mail.outbox[0].body

    def test_email_lookup_is_case_insensitive(self, api_client, user):
        response = api_client.post(REQUEST_URL, {"email": user.email.upper()})
        assert response.status_code == 200
        assert len(mail.outbox) == 1

    def test_unknown_email_gets_same_response_and_no_email(self, api_client, user):
        known = api_client.post(REQUEST_URL, {"email": user.email})
        unknown = api_client.post(REQUEST_URL, {"email": "nobody@example.com"})
        assert unknown.status_code == 200
        assert unknown.data == known.data
        assert len(mail.outbox) == 1  # only the known address

    def test_inactive_user_gets_no_email(self, api_client, user):
        user.is_active = False
        user.save()
        response = api_client.post(REQUEST_URL, {"email": user.email})
        assert response.status_code == 200
        assert len(mail.outbox) == 0

    def test_invalid_email_is_400(self, api_client):
        assert api_client.post(REQUEST_URL, {"email": "not-an-email"}).status_code == 400

    def test_works_with_a_stale_bearer_token(self, api_client, user):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not.a.real.token")
        assert api_client.post(REQUEST_URL, {"email": user.email}).status_code == 200


@pytest.mark.django_db
class TestPasswordResetConfirm:
    def test_link_from_email_resets_password(self, api_client, user):
        api_client.post(REQUEST_URL, {"email": user.email})
        uid, token = re.search(r"uid=([^&\s]+)&token=(\S+)", mail.outbox[0].body).groups()

        response = api_client.post(CONFIRM_URL, {"uid": uid, "token": token, "password": "BrandNewPass456!"})
        assert response.status_code == 200

        user.refresh_from_db()
        assert user.check_password("BrandNewPass456!")
        login = api_client.post("/api/auth/login/", {"email": user.email, "password": "BrandNewPass456!"})
        assert login.status_code == 200

    def test_token_works_only_once(self, api_client, user):
        uid, token = _uid_token(user)
        first = api_client.post(CONFIRM_URL, {"uid": uid, "token": token, "password": "BrandNewPass456!"})
        second = api_client.post(CONFIRM_URL, {"uid": uid, "token": token, "password": "AnotherPass789!"})
        assert first.status_code == 200
        assert second.status_code == 400

    def test_bad_token_is_400(self, api_client, user):
        uid, _ = _uid_token(user)
        response = api_client.post(CONFIRM_URL, {"uid": uid, "token": "bad-token", "password": "BrandNewPass456!"})
        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password("testpass123")

    def test_garbage_uid_is_400(self, api_client, user):
        _, token = _uid_token(user)
        response = api_client.post(CONFIRM_URL, {"uid": "!!!", "token": token, "password": "BrandNewPass456!"})
        assert response.status_code == 400

    def test_weak_password_is_400_and_token_still_valid(self, api_client, user):
        uid, token = _uid_token(user)
        weak = api_client.post(CONFIRM_URL, {"uid": uid, "token": token, "password": "123"})
        assert weak.status_code == 400
        assert "password" in weak.data
        ok = api_client.post(CONFIRM_URL, {"uid": uid, "token": token, "password": "BrandNewPass456!"})
        assert ok.status_code == 200


def test_brevo_backend_posts_to_api(monkeypatch, settings):
    from django.core.mail import EmailMessage

    from apps.accounts import email_backends

    settings.BREVO_API_KEY = "test-key"
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse()

    monkeypatch.setattr(email_backends.requests, "post", fake_post)
    message = EmailMessage("Subject", "Body", "SimplyFind <sender@example.com>", ["to@example.com"])
    sent = email_backends.BrevoEmailBackend().send_messages([message])

    assert sent == 1
    assert calls[0]["url"] == email_backends.BREVO_SEND_URL
    assert calls[0]["headers"]["api-key"] == "test-key"
    assert calls[0]["json"]["sender"] == {"name": "SimplyFind", "email": "sender@example.com"}
    assert calls[0]["json"]["to"] == [{"email": "to@example.com"}]
