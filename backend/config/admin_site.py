"""
SimplyFind's admin site: Django's own, with a dashboard on the home page,
the site's branding, and two-step sign-in. Installed in place of the
default site by config.apps.EELAdminConfig, so every @admin.register keeps
working.
"""

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.utils.html import format_html

from .dashboard import dashboard_context


def pill(text, tone="quiet"):
    """A coloured status pill for list columns. tone: ok / warn / bad / quiet
    (styles in templates/admin/base_site.html)."""
    return format_html('<span class="eel-pill eel-pill--{}">{}</span>', tone, text)


class TwoStepAdminLoginForm(AdminAuthenticationForm):
    """The admin holds everyone's data, so staff sign in with a two-step code
    too. Staff without two-step sign-in set it up first through the site
    (or `manage.py setup_mfa <email>`)."""

    otp = forms.CharField(
        label="Two-step code", required=False, max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
        help_text="The six-digit code from your authenticator app, or a recovery code.",
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        from apps.accounts import mfa

        if not settings.REQUIRE_MFA_FOR_STAFF_AND_COMPANIES and not user.mfa_enabled:
            return
        if not user.mfa_enabled:
            raise forms.ValidationError(
                "Set up two-step sign-in before using the admin (manage.py setup_mfa <email>).",
                code="mfa_setup_required",
            )
        if not mfa.verify(user, self.cleaned_data.get("otp")):
            raise forms.ValidationError("Enter a current two-step code.", code="mfa_required")


class EELAdminSite(admin.AdminSite):
    site_header = "SimplyFind admin"
    site_title = "SimplyFind admin"
    index_title = "Dashboard"
    login_form = TwoStepAdminLoginForm

    @property
    def site_url(self):
        # "View site" goes to the React frontend, not the API host's root.
        return settings.FRONTEND_URL

    def index(self, request, extra_context=None):
        return super().index(request, {**dashboard_context(request), **(extra_context or {})})
