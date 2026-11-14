from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings


class OptionalJWTAuthentication(JWTAuthentication):
    """
    JWT authentication that treats a bad token as "no token".

    Plain simplejwt raises a 401 from ``authenticate()`` as soon as it sees an
    expired or malformed Bearer token, which happens before DRF checks the
    view's permission classes. So a stale token in the browser made even
    AllowAny / read-only endpoints (opportunity list, categories, stats)
    return 401.

    Here an invalid token makes the request anonymous instead. Public views
    then answer normally, and protected views still return 401 through
    IsAuthenticated, because ``authenticate_header`` is inherited and DRF
    turns NotAuthenticated into a 401 with a WWW-Authenticate header.
    """

    def authenticate(self, request):
        try:
            if self.get_header(request) is not None:
                return super().authenticate(request)
            return self._authenticate_cookie(request)
        except (InvalidToken, AuthenticationFailed):
            return None

    def _authenticate_cookie(self, request):
        """The browser's HttpOnly session cookie (apps/accounts/sessions.py).
        The browser sends cookies by itself, so a state-changing request
        must also prove it came from our frontend: the CSRF token."""
        raw = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not raw:
            return None
        validated = self.get_validated_token(raw.encode())
        user = self.get_user(validated)
        self._enforce_csrf(request)
        return user, validated

    @staticmethod
    def _enforce_csrf(request):
        def dummy_get_response(_request):  # pragma: no cover - never called
            return None

        check = CSRFCheck(dummy_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            # Not swallowed by authenticate(): a forged request must fail loudly.
            raise exceptions.PermissionDenied(f"CSRF failed: {reason}")

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.token_is_current(validated_token.get("iat")):
            raise AuthenticationFailed("Token issued before the password was reset.", code="token_not_valid")
        return user


class CurrentTokenRefreshSerializer(TokenRefreshSerializer):
    """Refreshing also honours the cut-off: a refresh token from before a
    password reset (or for a deactivated account) can't mint new tokens."""

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.get(api_settings.USER_ID_CLAIM)
        user = get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
        if user is None or not user.is_active or not user.token_is_current(refresh.get("iat")):
            raise InvalidToken("Token is no longer valid. Please sign in again.")
        return super().validate(attrs)
