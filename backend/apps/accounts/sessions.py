"""
Sign-in sessions as HttpOnly cookies.

The access and refresh tokens never reach JavaScript: an injected script
can't read or send them anywhere. Because the browser attaches cookies by
itself, every state-changing request authenticated by cookie must also
carry the CSRF token (X-CSRFToken header), checked in
authentication.OptionalJWTAuthentication. The frontend gets that token
from GET /api/auth/csrf/.

An `Authorization: Bearer` header still works for API clients that aren't
browsers; those get no cookies to forge, so no CSRF check applies.
"""

from django.conf import settings
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.tokens import RefreshToken


def _cookie_args(max_age, path="/"):
    return {
        "max_age": int(max_age.total_seconds()),
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN or None,
        "path": path,
    }


def issue_session(response, user, *, mfa: bool = False):
    """Sign `user` in on `response`. `mfa`: this sign-in passed two-step
    verification (needed for company and staff endpoints)."""
    refresh = RefreshToken.for_user(user)
    if mfa:
        refresh["mfa"] = True
    access = refresh.access_token  # copies the mfa claim
    set_tokens(response, str(access), str(refresh))
    update_last_login(None, user)
    return response


def set_tokens(response, access: str, refresh: str | None = None):
    jwt = settings.SIMPLE_JWT
    response.set_cookie(settings.AUTH_ACCESS_COOKIE, access, **_cookie_args(jwt["ACCESS_TOKEN_LIFETIME"]))
    if refresh:
        response.set_cookie(settings.AUTH_REFRESH_COOKIE, refresh,
                            **_cookie_args(jwt["REFRESH_TOKEN_LIFETIME"], path=settings.AUTH_REFRESH_COOKIE_PATH))
    return response


def clear_session(response):
    domain = settings.AUTH_COOKIE_DOMAIN or None
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE, path="/", domain=domain,
                           samesite=settings.AUTH_COOKIE_SAMESITE)
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=settings.AUTH_REFRESH_COOKIE_PATH, domain=domain,
                           samesite=settings.AUTH_COOKIE_SAMESITE)
    return response
