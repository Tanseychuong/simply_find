"""
Email verification. Registration doesn't prove the address belongs to the
person signing up, so applying to jobs and creating a company wait until
the emailed link is opened. Google sign-in, a password reset and accepting
a team invitation also prove the mailbox, so they verify it too.
"""

import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

SALT = "simplyfind.verify-email"
MAX_AGE_SECONDS = 3 * 24 * 3600


def make_token(user) -> str:
    # Tied to the address: changing the email makes old links useless.
    return signing.dumps({"u": user.pk, "e": user.email.lower()}, salt=SALT)


def user_for_token(token: str):
    from .models import User
    try:
        data = signing.loads(token or "", salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or user.email.lower() != data.get("e"):
        return None
    return user


def mark_verified(user) -> None:
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])


def send_verification_email(user) -> None:
    link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={make_token(user)}"

    def _send():
        try:
            send_mail(
                subject="Confirm your SimplyFind email",
                message=(
                    f"Hi {user.name},\n\n"
                    "Welcome to SimplyFind. Open this link to confirm your email address "
                    "(it works for 3 days):\n\n"
                    f"{link}\n\n"
                    "You need a confirmed email before you can apply for roles.\n\n"
                    "If you didn't create this account, you can ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        except Exception:
            logger.exception("Verification email failed for user %s", user.pk)

    transaction.on_commit(_send)


def require_verified_email(user) -> None:
    if settings.REQUIRE_VERIFIED_EMAIL and user.email_verified_at is None:
        raise PermissionDenied({
            "detail": "Confirm your email address first. We sent you a link when you signed up.",
            "code": "email_not_verified",
        })
