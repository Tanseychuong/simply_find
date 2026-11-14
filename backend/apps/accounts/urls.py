from django.urls import path

from .views import (
    CsrfView,
    DeleteAccountView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    MeView,
    MfaDisableView,
    MfaEnableView,
    MfaLoginView,
    MfaSetupView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
)

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("verify-email/resend/", ResendVerificationView.as_view(), name="verify-email-resend"),
    path("mfa/login/", MfaLoginView.as_view(), name="mfa-login"),
    path("mfa/setup/", MfaSetupView.as_view(), name="mfa-setup"),
    path("mfa/enable/", MfaEnableView.as_view(), name="mfa-enable"),
    path("mfa/disable/", MfaDisableView.as_view(), name="mfa-disable"),
    path("me/", MeView.as_view(), name="me"),
    path("me/delete/", DeleteAccountView.as_view(), name="me-delete"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
