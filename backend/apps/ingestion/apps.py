import os
import sys

from django.apps import AppConfig
from django.conf import settings


class IngestionConfig(AppConfig):
    name = "apps.ingestion"
    label = "ingestion"
    verbose_name = "Ingestion"

    def ready(self):
        # Dev only: start the worker inside `runserver` so opportunities are
        # fetched automatically without a second terminal. RUN_MAIN is set
        # in the autoreloader's child process — the one that serves requests
        # — so this doesn't start twice. Never runs for migrate, tests, etc.
        if not getattr(settings, "INGESTION_AUTOSTART", False):
            return
        if "runserver" not in sys.argv:
            return
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in sys.argv:
            return
        from .worker import start_background_worker

        start_background_worker()
