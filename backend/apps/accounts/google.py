"""
"Sign in with Google".

The browser gets an ID token (a JWT signed by Google) from Google's own
sign-in button and posts it to /api/auth/google/. We check the signature
against Google's published keys, the audience (our client ID), issuer,
expiry, and that Google has verified the email, then sign the user in.

Google's keys are cached (for as long as Google's Cache-Control allows) and
fetched with a short timeout, so a sign-in normally makes no outbound call
and a slow Google can't tie up a server worker for long.

Account matching, in order:
1. A user already linked to this Google account (``google_sub``).
2. A user with the same email:
   - with a password: linked only once they also enter that password.
     Registration doesn't verify email addresses, so someone could sign up
     with another person's email first. Asking for the password stops that
     account being silently handed to the real owner while the first
     person still knows its password. A forgotten password goes through the
     normal reset, which emails the real owner and ends the other sessions.
   - with no password: linked straight away, except staff accounts, which
     are never linked without their password.
   - more than one account differing only by letter case: refused.
3. Otherwise a new account, with no password.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction

from .models import User

logger = logging.getLogger(__name__)

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
CERTS_CACHE_KEY = "google-signin-certs"
# After an unknown key id, refetch at most this often (Google rotates keys;
# this stops junk tokens from turning into a stream of outbound requests).
CERTS_REFETCH_KEY = "google-signin-certs-refetched"
CERTS_REFETCH_INTERVAL = 60
FETCH_TIMEOUT = 5
# A Google confirmation for a sensitive action (deleting the account) must
# be this fresh, so an older sign-in token can't be replayed for it.
CONFIRMATION_MAX_AGE = 300

GENERIC_FAILURE = "Google sign-in failed or expired. Please try again."


class GoogleSignInError(Exception):
    """A sign-in we refuse. ``code`` lets the frontend react; ``detail`` is
    safe to show."""

    def __init__(self, detail: str, code: str = "google_failed", status: int = 400, **extra):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status = status
        self.extra = extra


def is_enabled() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID)


# --- Google's signing keys --------------------------------------------------

def _fetch_certs() -> tuple[dict, int]:
    """Download Google's current public keys. Returns (certs, max_age)."""
    response = requests.get(CERTS_URL, timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    certs = response.json()
    if not isinstance(certs, dict) or not certs:
        raise ValueError("Unexpected certificate response from Google")
    match = re.search(r"max-age=(\d+)", response.headers.get("Cache-Control", ""))
    max_age = int(match.group(1)) if match else 3600
    return certs, max(60, min(max_age, 86400))


def _certs_for(kid: str | None) -> dict:
    certs = cache.get(CERTS_CACHE_KEY)
    stale = certs is None or (kid is not None and kid not in certs
                              and cache.add(CERTS_REFETCH_KEY, True, CERTS_REFETCH_INTERVAL))
    if stale:
        try:
            certs, max_age = _fetch_certs()
        except (requests.RequestException, ValueError):
            logger.exception("Couldn't fetch Google's sign-in keys")
            raise GoogleSignInError("We couldn't reach Google. Please try again.", status=503)
        cache.set(CERTS_CACHE_KEY, certs, max_age)
    return certs


def _key_id(credential: str) -> str | None:
    """The token header's key id, read before verification only to pick a key."""
    try:
        segment = credential.split(".", 1)[0]
        header = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    except (ValueError, UnicodeDecodeError):
        raise GoogleSignInError(GENERIC_FAILURE)
    kid = header.get("kid") if isinstance(header, dict) else None
    return kid if isinstance(kid, str) else None


def _decode(credential: str) -> dict:
    """Verify signature, audience and expiry; return the claims."""
    from google.auth import exceptions as google_exceptions
    from google.auth import jwt as google_jwt

    certs = _certs_for(_key_id(credential))
    try:
        return google_jwt.decode(credential, certs=certs, audience=settings.GOOGLE_CLIENT_ID,
                                 clock_skew_in_seconds=10)
    except (ValueError, google_exceptions.GoogleAuthError):
        # Bad signature, unknown key, wrong audience, expired, malformed.
        raise GoogleSignInError(GENERIC_FAILURE)


def verify_credential(credential) -> dict:
    """Return the token's verified claims, or raise GoogleSignInError."""
    if not is_enabled():
        raise GoogleSignInError("Google sign-in isn't available right now.", code="google_disabled", status=503)
    if not credential or not isinstance(credential, str) or len(credential) > 4096:
        raise GoogleSignInError(GENERIC_FAILURE)

    claims = _decode(credential)
    if claims.get("iss") not in GOOGLE_ISSUERS or not claims.get("sub"):
        raise GoogleSignInError(GENERIC_FAILURE)
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise GoogleSignInError("Your Google account's email address isn't verified.", code="email_unverified")
    return claims


# --- Accounts ---------------------------------------------------------------

def _display_name(claims: dict) -> str:
    name = (claims.get("name") or "").strip()
    if not name:
        name = " ".join(p for p in (claims.get("given_name"), claims.get("family_name")) if p).strip()
    return (name or claims["email"].split("@", 1)[0])[:120]


def _check_active(user: User) -> None:
    if not user.is_active:
        # Same wording as a password sign-in for a deactivated account.
        raise GoogleSignInError("No active account found with the given credentials", code="inactive", status=401)


def _account_for_email(email: str) -> User | None:
    matches = list(User.objects.filter(email__iexact=email)[:3])
    if len(matches) <= 1:
        return matches[0] if matches else None
    exact = [u for u in matches if u.email == email]
    if len(exact) == 1:
        return exact[0]
    raise GoogleSignInError(
        "We couldn't match your Google account to a single account. Please sign in with your password or contact us.",
        code="ambiguous_email", status=409,
    )


def sign_in(claims: dict, password: str | None = None) -> tuple[User, bool]:
    """Find, link or create the user for verified Google claims.
    Returns (user, created)."""
    sub = claims["sub"]
    email = User.objects.normalize_email(claims["email"])

    user = User.objects.filter(google_sub=sub).first()
    if user is not None:
        _check_active(user)
        return user, False

    user = _account_for_email(email)
    if user is not None:
        _check_active(user)
        if user.google_sub:
            # The email belongs to an account linked to a different Google login.
            raise GoogleSignInError(
                "This email is linked to a different Google account. Sign in with that one or with your password.",
                code="other_google_account", status=409,
            )
        if user.has_usable_password():
            if not password:
                raise GoogleSignInError(
                    "You already have an account with this email. Enter its password once to link Google.",
                    code="link_required", status=409, email=user.email,
                )
            if not user.check_password(password):
                raise GoogleSignInError("That password isn't right.", code="link_password_wrong", status=400,
                                        email=user.email)
        elif user.is_staff or user.is_superuser:
            # A staff account without a password (e.g. created by
            # `createsuperuser --noinput`) is never claimed by email alone.
            raise GoogleSignInError(
                "This account can't be linked to Google automatically. Please contact an administrator.",
                code="staff_link_refused", status=403,
            )
        user.google_sub = sub
        user.save(update_fields=["google_sub"])
        return user, False

    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, name=_display_name(claims), password=None)
            user.google_sub = sub
            user.save(update_fields=["google_sub"])
    except IntegrityError:
        # Two sign-ins racing (double click): the other one created it.
        user = User.objects.filter(google_sub=sub).first()
        if user is None:
            raise GoogleSignInError("Google sign-in failed. Please try again.")
        _check_active(user)
        return user, False
    return user, True


def credential_matches_user(credential, user: User) -> bool:
    """Re-authentication for accounts without a password (e.g. deleting the
    account): a Google sign-in as the same Google account, made in the last
    few minutes."""
    if not user.google_sub:
        return False
    try:
        claims = verify_credential(credential)
    except GoogleSignInError:
        return False
    issued_at = claims.get("iat")
    if not isinstance(issued_at, (int, float)) or time.time() - issued_at > CONFIRMATION_MAX_AGE:
        return False
    return claims["sub"] == user.google_sub
