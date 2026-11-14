"""
OptionalJWTAuthentication: an expired or garbage Bearer token must not 401
public endpoints, but protected endpoints still 401.
"""

import pytest
from rest_framework_simplejwt.tokens import AccessToken

BAD_TOKEN = "Bearer not.a.real.token"


@pytest.fixture
def bad_token_client(api_client):
    api_client.credentials(HTTP_AUTHORIZATION=BAD_TOKEN)
    return api_client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/api/opportunities/",
        "/api/opportunities/categories/",
        "/api/opportunities/stats/",
    ],
)
def test_public_endpoints_ignore_bad_token(bad_token_client, category, url):
    response = bad_token_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_me_with_bad_token_is_401(bad_token_client):
    response = bad_token_client.get("/api/auth/me/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response


@pytest.mark.django_db
def test_write_with_bad_token_is_rejected(bad_token_client, category):
    response = bad_token_client.post(
        "/api/opportunities/",
        {"title": "Should not be created", "category": category.pk},
        format="json",
    )
    assert response.status_code in (401, 403)


def test_me_with_real_token_is_200(api_client, user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    response = api_client.get("/api/auth/me/")
    assert response.status_code == 200


def test_me_with_force_authenticate_is_200(api_client, user):
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/auth/me/")
    assert response.status_code == 200
