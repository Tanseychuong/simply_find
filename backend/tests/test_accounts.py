import pytest


@pytest.mark.django_db
class TestRegistration:
    def test_register_creates_user(self, api_client):
        response = api_client.post("/api/auth/register/", {
            "name": "New User", "email": "new@example.com", "password": "StrongPass123!",
        })
        assert response.status_code == 201
        assert response.data["user"]["email"] == "new@example.com"
        assert response.data["user"]["email_verified"] is False

    def test_register_rejects_weak_password(self, api_client):
        response = api_client.post("/api/auth/register/", {
            "name": "New User", "email": "weak@example.com", "password": "123",
        })
        assert response.status_code == 400

    def test_register_rejects_duplicate_email(self, api_client, user):
        response = api_client.post("/api/auth/register/", {
            "name": "Dupe", "email": user.email, "password": "StrongPass123!",
        })
        assert response.status_code == 400


@pytest.mark.django_db
class TestLogin:
    def test_login_sets_httponly_cookies_not_body_tokens(self, api_client, user):
        response = api_client.post("/api/auth/login/", {"email": user.email, "password": "testpass123"})
        assert response.status_code == 200
        assert response.data["user"]["email"] == user.email
        assert "access" not in response.data and "refresh" not in response.data
        access, refresh = response.cookies["sf_access"], response.cookies["sf_refresh"]
        assert access["httponly"] and refresh["httponly"]
        assert refresh["path"] == "/api/auth/"   # the refresh token only goes to auth endpoints

    def test_login_wrong_password_fails(self, api_client, user):
        response = api_client.post("/api/auth/login/", {"email": user.email, "password": "wrong"})
        assert response.status_code == 401

    def test_repeated_login_attempts_are_throttled(self, api_client, user):
        statuses = [
            api_client.post("/api/auth/login/", {"email": user.email, "password": "wrong"}).status_code
            for _ in range(11)
        ]
        assert statuses[:10] == [401] * 10
        assert statuses[10] == 429


@pytest.mark.django_db
class TestMe:
    def test_me_requires_auth(self, api_client):
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401

    def test_me_returns_profile(self, api_client, user):
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["email"] == user.email
        assert response.data["role"] == "user"

    def test_me_shows_admin_role(self, api_client, admin_user):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get("/api/auth/me/")
        assert response.data["role"] == "admin"

    def test_me_shows_moderator_role(self, api_client, moderator_user):
        api_client.force_authenticate(user=moderator_user)
        response = api_client.get("/api/auth/me/")
        assert response.data["role"] == "moderator"


def _png(size_bytes=0):
    from io import BytesIO
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return SimpleUploadedFile("avatar.png", buf.getvalue() + b"\0" * size_bytes, content_type="image/png")


@pytest.mark.django_db
class TestProfilePicture:
    def test_upload_returns_absolute_url(self, api_client, user, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        api_client.force_authenticate(user=user)
        response = api_client.patch("/api/auth/me/", {"profile_picture": _png()}, format="multipart")
        assert response.status_code == 200
        assert response.data["profile_picture"].startswith("http")
        assert "profile_pics/" in response.data["profile_picture"] and "avatar" not in response.data["profile_picture"]

    def test_oversized_upload_rejected(self, api_client, user, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        settings.MAX_UPLOAD_MB = 1
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            "/api/auth/me/", {"profile_picture": _png(size_bytes=1024 * 1024)}, format="multipart",
        )
        assert response.status_code == 400
        assert "profile_picture" in response.data
