from django.contrib.admin.apps import AdminConfig


class SimplyFindAdminConfig(AdminConfig):
    default_site = "config.admin_site.SimplyFindAdminSite"
