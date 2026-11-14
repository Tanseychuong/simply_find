from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    verbose_name = "Student documents"

    def ready(self):
        from . import checks  # noqa: F401  (registers the deploy checks)
