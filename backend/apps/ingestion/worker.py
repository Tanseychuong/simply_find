"""
The long-running loop behind `python manage.py run_ingestion_worker`
(production: its own process) and the optional background thread started
by `runserver` in development (INGESTION_AUTOSTART).
"""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections

from .scheduler import run_cycle

logger = logging.getLogger(__name__)

_thread_started = False
_thread_lock = threading.Lock()


def run_forever(stop_event: threading.Event, interval: int | None = None, once: bool = False) -> bool:
    """Returns whether the last cycle completed, so `--once` (the scheduled
    GitHub Action) can fail loudly instead of reporting a crash as success."""
    interval = interval or settings.INGESTION_WORKER_INTERVAL_SECONDS
    ok = True
    while not stop_event.is_set():
        close_old_connections()  # never reuse a connection the DB has dropped
        try:
            summary = run_cycle(
                source_limit=settings.INGESTION_SOURCE_BATCH,
                enrich_limit=settings.INGESTION_ENRICH_BATCH,
            )
            ok = True
            if any(summary.values()):
                logger.info("Ingestion cycle: %s", summary)
        except Exception:  # noqa: BLE001 — the worker must survive DB blips, bad feeds, etc.
            ok = False
            logger.exception("Ingestion cycle crashed; retrying in %ss", interval)
        if once:
            break
        stop_event.wait(interval)
    close_old_connections()
    return ok


def start_background_worker() -> None:
    """Dev convenience: run the worker inside `runserver` so fetching is
    automatic without a second terminal. Production runs the management
    command as a separate process instead (see docs/ingestion.md)."""
    global _thread_started
    with _thread_lock:
        if _thread_started:
            return
        _thread_started = True
    thread = threading.Thread(
        target=run_forever, args=(threading.Event(),), name="eel-ingestion-worker", daemon=True,
    )
    thread.start()
    logger.info("Started in-process ingestion worker (INGESTION_AUTOSTART=True)")
