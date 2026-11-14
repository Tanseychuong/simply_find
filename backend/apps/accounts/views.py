import logging

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import google

from .models import User
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    throttle_scope = "auth"


class GoogleLoginView(generics.GenericAPIView):
    """POST /api/auth/google/ {credential, password?} -> {access, refresh, created}.

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

        refresh = RefreshToken.for_user(user)
        update_last_login(None, user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh), "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
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
                    subject="Reset your Global Opportunities password",
                    message=(
                        f"Hi {user.name},\n\n"
                        "We received a request to reset your Global Opportunities password. "
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
        user.save(update_fields=["password", "tokens_valid_after"])
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
