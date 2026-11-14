from django.contrib.admin.apps import AdminConfig


class EELAdminConfig(AdminConfig):
    default_site = "config.admin_site.EELAdminSite"
