"""
Two-step sign-in (TOTP, the six-digit codes from Google Authenticator,
Microsoft Authenticator, Authy and similar apps).

Who needs it: staff, moderators and everyone on a company's team
(`mfa_required_for`). They can sign in without it, but endpoints that
reach applicants' data or moderation only answer a session that passed
two-step sign-in (`session_has_mfa`); others get 403 with code
`mfa_required` or `mfa_setup_required`, which the frontend turns into the
right screen.

The secret is stored encrypted with a key derived from SECRET_KEY, so a
database leak alone doesn't hand out working codes. Each code works once
(the last used time step is remembered), and ten single-use recovery
codes, stored hashed, cover a lost phone.
"""

import base64
import hashlib
import secrets

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.utils import timezone

ISSUER = "SimplyFind"
RECOVERY_CODE_COUNT = 10
LOGIN_CHALLENGE_SALT = "simplyfind.mfa-login"
LOGIN_CHALLENGE_SECONDS = 300


def _fernet() -> Fernet:
    key = hashlib.sha256(f"simplyfind-mfa:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mfa_required_for(user) -> bool:
    if not settings.REQUIRE_MFA_FOR_STAFF_AND_COMPANIES or not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    from apps.companies.models import CompanyMembership
    return CompanyMembership.objects.filter(user=user).exists()


def session_has_mfa(request) -> bool:
    """Did this request's sign-in pass two-step verification?"""
    token = getattr(request, "auth", None)
    return bool(token is not None and hasattr(token, "get") and token.get("mfa"))


def require_mfa(request) -> None:
    """Raise 403 {detail, code} unless the request may reach endpoints that
    expose applicants' data or moderation."""
    from rest_framework.exceptions import PermissionDenied

    problem = mfa_problem(request)
    if problem == "mfa_setup_required":
        raise PermissionDenied({"detail": "Set up two-step sign-in to use company and staff tools.", "code": problem})
    if problem:
        raise PermissionDenied({"detail": "Sign in again with your two-step code to continue.", "code": problem})


def mfa_problem(request) -> str | None:
    """None if the request may reach MFA-protected endpoints, else the code
    to send back: mfa_setup_required (not set up yet) or mfa_required."""
    user = request.user
    if not mfa_required_for(user) or session_has_mfa(request):
        return None
    return "mfa_required" if user.mfa_enabled else "mfa_setup_required"


def start_setup(user) -> dict:
    secret = pyotp.random_base32()
    user.mfa_secret = encrypt(secret)
    user.mfa_enabled_at = None
    user.mfa_recovery_codes = []
    user.mfa_last_step = None
    user.save(update_fields=["mfa_secret", "mfa_enabled_at", "mfa_recovery_codes", "mfa_last_step"])
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    # An inline SVG QR code for the authenticator app, made here so the
    # secret never goes to a third-party QR service.
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": segno.make(uri, error="m").svg_inline(scale=4)}


def _check_totp(user, code: str) -> bool:
    secret = decrypt(user.mfa_secret or "")
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    now = timezone.now()
    for offset in (0, -1, 1):   # one step of clock drift either way
        step = totp.timecode(now) + offset
        if step <= (user.mfa_last_step or -1):
            continue  # each code works once
        if secrets.compare_digest(totp.generate_otp(step), code):
            user.mfa_last_step = step
            user.save(update_fields=["mfa_last_step"])
            return True
    return False


def _use_recovery_code(user, code: str) -> bool:
    code = code.replace("-", "").replace(" ", "").lower()
    for stored in user.mfa_recovery_codes or []:
        if check_password(code, stored):
            user.mfa_recovery_codes = [c for c in user.mfa_recovery_codes if c != stored]
            user.save(update_fields=["mfa_recovery_codes"])
            return True
    return False


def verify(user, code) -> bool:
    """A six-digit code from the app, or a recovery code."""
    code = str(code or "").strip()
    if not code:
        return False
    if code.isdigit() and len(code) == 6:
        return _check_totp(user, code)
    return user.mfa_enabled and _use_recovery_code(user, code)


def enable(user, code) -> list[str] | None:
    """Confirm setup with a first code. Returns the recovery codes (shown
    once), or None if the code is wrong."""
    if not user.mfa_secret or not _check_totp(user, str(code or "").strip()):
        return None
    codes = [secrets.token_hex(5) for _ in range(RECOVERY_CODE_COUNT)]
    user.mfa_recovery_codes = [make_password(c) for c in codes]
    user.mfa_enabled_at = timezone.now()
    user.save(update_fields=["mfa_recovery_codes", "mfa_enabled_at"])
    return [f"{c[:5]}-{c[5:]}" for c in codes]


def disable(user) -> None:
    user.mfa_secret = ""
    user.mfa_enabled_at = None
    user.mfa_recovery_codes = []
    user.mfa_last_step = None
    user.save(update_fields=["mfa_secret", "mfa_enabled_at", "mfa_recovery_codes", "mfa_last_step"])


def login_challenge(user) -> str:
    """Proof that the password (or Google) step passed, exchanged for a
    session once the code is entered. Short-lived and tied to the current
    password, so it dies if the password changes."""
    return signing.dumps({"u": user.pk, "p": (user.password or "")[-12:]}, salt=LOGIN_CHALLENGE_SALT)


def user_for_challenge(token: str):
    from .models import User
    try:
        data = signing.loads(token or "", salt=LOGIN_CHALLENGE_SALT, max_age=LOGIN_CHALLENGE_SECONDS)
    except signing.BadSignature:
        return None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or (user.password or "")[-12:] != data.get("p") or not user.mfa_enabled:
        return None
    return user
