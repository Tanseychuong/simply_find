from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def application_files_are_private(app_configs, **kwargs):
    """CVs are personal data: warn while they share the public media bucket."""
    if settings.DEBUG or settings.STORAGES["applications"] is not settings.STORAGES["default"]:
        return []
    return [Warning(
        "Application files (CVs) are stored in the same storage as public media.",
        hint="Create a PRIVATE Supabase bucket and set SUPABASE_PRIVATE_BUCKET.",
        id="companies.W001",
    )]
