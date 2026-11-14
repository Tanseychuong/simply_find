from django.apps import AppConfig


class CompaniesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.companies"
    verbose_name = "Companies & applications"

    def ready(self):
        from . import checks, signals  # noqa: F401  (registers the check and signal handlers)
