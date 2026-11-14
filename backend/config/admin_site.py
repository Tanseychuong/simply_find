"""
EEL's admin site: Django's own, with a dashboard on the home page and the
site's branding. Installed in place of the default site by
config.apps.EELAdminConfig, so every @admin.register keeps working.
"""

from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html

from .dashboard import dashboard_context


def pill(text, tone="quiet"):
    """A coloured status pill for list columns. tone: ok / warn / bad / quiet
    (styles in templates/admin/base_site.html)."""
    return format_html('<span class="eel-pill eel-pill--{}">{}</span>', tone, text)


class EELAdminSite(admin.AdminSite):
    site_header = "Global Opportunities admin"
    site_title = "Global Opportunities admin"
    index_title = "Dashboard"

    @property
    def site_url(self):
        # "View site" goes to the React frontend, not the API host's root.
        return settings.FRONTEND_URL

    def index(self, request, extra_context=None):
        return super().index(request, {**dashboard_context(request), **(extra_context or {})})
