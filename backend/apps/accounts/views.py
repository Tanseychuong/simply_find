import logging

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import generics, permissions, status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import google, mfa, verification
from .authentication import CurrentTokenRefreshSerializer
from .sessions import clear_session, issue_session, set_tokens

from .models import User
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


def _signed_in(user, *, status_code=status.HTTP_200_OK, mfa_passed=False, **extra):
    """The response for a finished sign-in: session cookies + the user."""
    response = Response({"user": UserSerializer(user).data, **extra}, status=status_code)
    return issue_session(response, user, mfa=mfa_passed)


def _password_or_mfa_step(user, *, status_code=status.HTTP_200_OK, **extra):
    """After the password (or Google) step: sign in, or ask for the code."""
    if user.mfa_enabled:
        return Response({"mfa_required": True, "mfa_token": mfa.login_challenge(user), **extra}, status=status_code)
    return _signed_in(user, status_code=status_code, **extra)


class CsrfView(APIView):
    """GET /api/auth/csrf/ -> {csrfToken}. Sets the CSRF cookie; the
    frontend sends the token back as X-CSRFToken on every POST/PATCH/DELETE
    (needed because the session lives in cookies)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ {name, email, password} -> signed in, with a
    confirmation email on its way."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if request.data.get("drive"):
            # Signed up from a recruitment drive's QR code (apps/drives).
            from apps.drives.services import record_self_signup
            record_self_signup(str(request.data["drive"]), user)
        verification.send_verification_email(user)
        return _signed_in(user, status_code=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ {email, password} -> {user} + session cookies,
    or {mfa_required, mfa_token} when two-step sign-in is on."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        email = str(request.data.get("email") or "").strip()
        password = str(request.data.get("password") or "")
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is None or not user.is_active or not user.check_password(password):
            if user is None:
                User().set_password(password)  # same time spent either way: no account probing by timing
            return Response({"detail": "That email and password don't match an account."},
                            status=status.HTTP_401_UNAUTHORIZED)
        return _password_or_mfa_step(user)


class MfaLoginView(APIView):
    """POST /api/auth/mfa/login/ {mfa_token, code} -> {user} + session cookies."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        user = mfa.user_for_challenge(request.data.get("mfa_token"))
        if user is None:
            return Response({"detail": "This sign-in has expired. Enter your password again.", "code": "mfa_expired"},
                            status=status.HTTP_401_UNAUTHORIZED)
        if not mfa.verify(user, request.data.get("code")):
            return Response({"detail": "That code isn't right. Check the time on your phone and try again."},
                            status=status.HTTP_400_BAD_REQUEST)
        return _signed_in(user, mfa_passed=True)


class RefreshView(APIView):
    """POST /api/auth/refresh/ -> new session cookies. The refresh token
    comes from its cookie (or {"refresh"} for non-browser clients), is
    used once, and rotated."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "refresh"

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE) or request.data.get("refresh")
        serializer = CurrentTokenRefreshSerializer(data={"refresh": raw or ""})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken, ValidationError):
            response = Response({"detail": "Your session has ended. Please sign in again."},
                                status=status.HTTP_401_UNAUTHORIZED)
            return clear_session(response)
        response = Response({"detail": "ok"})
        return set_tokens(response, serializer.validated_data["access"], serializer.validated_data.get("refresh"))


class LogoutView(APIView):
    """POST /api/auth/logout/ -> revokes the refresh token, clears the cookies."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE) or request.data.get("refresh")
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # already expired or revoked
        return clear_session(Response({"detail": "Signed out."}))


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email/ {token} — the link from the email."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        user = verification.user_for_token(request.data.get("token"))
        if user is None:
            return Response({"detail": "This link is invalid or has expired. Ask for a new one from your profile."},
                            status=status.HTTP_400_BAD_REQUEST)
        verification.mark_verified(user)
        return Response({"detail": "Your email is confirmed."})


class ResendVerificationView(APIView):
    """POST /api/auth/verify-email/resend/ — signed in, not yet confirmed."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        if request.user.email_verified:
            return Response({"detail": "Your email is already confirmed."})
        verification.send_verification_email(request.user)
        return Response({"detail": f"We've sent a new link to {request.user.email}."})


def _reauthenticated(request) -> bool:
    """Sensitive account changes ask for the password again (accounts made
    with Google: a current two-step code, if any)."""
    user = request.user
    if user.has_usable_password():
        return user.check_password(str(request.data.get("password") or ""))
    return True


class MfaSetupView(APIView):
    """POST /api/auth/mfa/setup/ {password} -> {secret, otpauth_uri} to put in
    an authenticator app (the frontend shows the URI as a QR code). Not on
    until confirmed with /mfa/enable/."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        if not _reauthenticated(request):
            return Response({"password": ["That password isn't right."]}, status=status.HTTP_400_BAD_REQUEST)
        if request.user.mfa_enabled:
            return Response({"detail": "Two-step sign-in is already on. Turn it off first to move it to a new phone."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(mfa.start_setup(request.user))


class MfaEnableView(APIView):
    """POST /api/auth/mfa/enable/ {code} -> {recovery_codes} (shown once) and
    a fresh session that counts as two-step verified."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        if request.user.mfa_enabled:
            return Response({"detail": "Two-step sign-in is already on."}, status=status.HTTP_400_BAD_REQUEST)
        codes = mfa.enable(request.user, request.data.get("code"))
        if codes is None:
            return Response({"code": ["That code isn't right. Check the time on your phone and try again."]},
                            status=status.HTTP_400_BAD_REQUEST)
        return _signed_in(request.user, mfa_passed=True, recovery_codes=codes)


class MfaDisableView(APIView):
    """POST /api/auth/mfa/disable/ {password, code}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if not user.mfa_enabled:
            return Response({"detail": "Two-step sign-in is already off."})
        if not _reauthenticated(request) or not mfa.verify(user, request.data.get("code")):
            return Response({"detail": "Enter your password and a current code to turn this off."},
                            status=status.HTTP_400_BAD_REQUEST)
        mfa.disable(user)
        user.tokens_valid_after = timezone.now()  # sessions that passed two-step sign-in end too
        user.save(update_fields=["tokens_valid_after"])
        return _signed_in(user)


class GoogleLoginView(generics.GenericAPIView):
    """POST /api/auth/google/ {credential, password?} -> {user, created} + session
    cookies, or {mfa_required, mfa_token} when two-step sign-in is on.

    ``credential`` is the ID token from Google's sign-in button. ``password``
    is only needed to link Google to an existing password account (see
    apps/accounts/google.py). Errors carry a ``code`` the frontend acts on,
    e.g. ``link_required``."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        try:
            claims = google.verify_credential(request.data.get("credential"))
            password = request.data.get("password")
            user, created = google.sign_in(claims, password if isinstance(password, str) else None)
        except google.GoogleSignInError as exc:
            return Response({"detail": exc.detail, "code": exc.code, **exc.extra}, status=exc.status)

        verification.mark_verified(user)  # Google only signs in verified addresses
        return _password_or_mfa_step(
            user, status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK, created=created,
        )


RESET_REQUEST_MESSAGE = "If an account exists for that email, we've sent a link to reset your password."


class PasswordResetRequestView(generics.GenericAPIView):
    """POST /api/auth/password-reset/ {email} — emails a reset link.

    Always answers the same way, whether or not the email has an account,
    so the endpoint can't be used to find out who is registered."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        # Accounts created with Google have no password; a reset lets them
        # set one, so losing access to Google never locks them out.
        if user is not None and (user.has_usable_password() or user.google_sub):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
            minutes = settings.PASSWORD_RESET_TIMEOUT // 60
            try:
                send_mail(
                    subject="Reset your SimplyFind password",
                    message=(
                        f"Hi {user.name},\n\n"
                        "We received a request to reset your SimplyFind password. "
                        f"Open this link to choose a new one (it expires in {minutes} minutes):\n\n"
                        f"{link}\n\n"
                        "If you didn't ask for this, you can ignore this email; "
                        "your password won't change."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                )
            except Exception:
                # Logged, not surfaced: the response must look the same
                # whether or not an email was sent.
                logger.exception("Password reset email failed for user %s", user.pk)

        return Response({"detail": RESET_REQUEST_MESSAGE})


class PasswordResetConfirmView(generics.GenericAPIView):
    """POST /api/auth/password-reset/confirm/ {uid, token, password}.

    The token is tied to the current password hash, so it stops working as
    soon as the password changes (one use only)."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.tokens_valid_after = timezone.now()  # end every existing session
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()  # the link reached their mailbox
        user.save(update_fields=["password", "tokens_valid_after", "email_verified_at"])
        return Response({"detail": "Your password has been reset. You can now sign in."}, status=status.HTTP_200_OK)


class DeleteAccountView(generics.GenericAPIView):
    """POST /api/auth/me/delete/ {password} or {google_credential}: deactivate
    now, delete after the hold (apps/accounts/deletion.py). Re-entering the
    password guards against someone using an unattended signed-in browser.
    Accounts without a password (created with Google) confirm with a fresh
    Google sign-in instead."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        from .deletion import DELETION_HOLD, request_deletion

        user = request.user
        if user.has_usable_password():
            password = request.data.get("password") or ""
            if not user.check_password(password):
                return Response({"password": ["That password isn't right."]}, status=status.HTTP_400_BAD_REQUEST)
        elif not google.credential_matches_user(request.data.get("google_credential") or "", user):
            return Response({"detail": "Confirm with the Google account you signed up with."},
                            status=status.HTTP_400_BAD_REQUEST)
        request_deletion(request.user)
        return Response({
            "detail": f"Your account is deactivated and will be permanently deleted in {DELETION_HOLD.days} days. "
                      "We've emailed you how to undo this.",
        })


class MeView(generics.RetrieveUpdateAPIView):
    """GET /api/auth/me — the logged-in user's own profile.
    PATCH /api/auth/me — update name and/or profile_picture (multipart for
    the picture; JSON works fine for name-only updates)."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def update(self, request, *args, **kwargs):
        # Always partial — a profile edit updates whichever fields were
        # sent, never requires every field present (no PUT semantics here).
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Respond with the full read shape (UserSerializer), not the
        # narrower write serializer, so the frontend can just drop the
        # response straight into its user state.
        return Response(UserSerializer(instance, context=self.get_serializer_context()).data)
