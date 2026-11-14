from django.conf import settings
from django.core.checks import Error, Warning, register


@register(deploy=True)
def uploads_are_scanned(app_configs, **kwargs):
    """Production expects a virus scanner. Without one, uploads are refused
    (VIRUS_SCAN_REQUIRED) unless that is explicitly switched off."""
    if settings.CLAMAV_HOST:
        return []
    if settings.VIRUS_SCAN_REQUIRED:
        return [Error(
            "VIRUS_SCAN_REQUIRED is on but CLAMAV_HOST is not set: every upload will be refused.",
            hint="Run a ClamAV (clamd) service and set CLAMAV_HOST/CLAMAV_PORT, or set "
                 "VIRUS_SCAN_REQUIRED=False knowingly for a demo.",
            id="documents.E001",
        )]
    return [Warning(
        "Uploads are not virus-scanned (no CLAMAV_HOST).",
        hint="Run a ClamAV (clamd) service and set CLAMAV_HOST before real students upload documents.",
        id="documents.W001",
    )]
