"""
Run via:
    python manage.py run_ingestion_worker            # loop forever (production worker process)
    python manage.py run_ingestion_worker --once     # one cycle, then exit (cron / manual)
    python manage.py run_ingestion_worker --interval 30

Each cycle fetches every source that's due (per its own interval) and
enriches every opportunity still waiting for its image/summary. Stops
cleanly on Ctrl-C or SIGTERM (what hosting platforms send on deploy).
"""

import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.worker import run_forever


class Command(BaseCommand):
    help = "Automatically fetch due sources and enrich new opportunities, on a loop."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run a single cycle and exit.")
        parser.add_argument("--interval", type=int, default=None, help="Seconds between cycles.")

    def handle(self, *args, **options):
        stop = threading.Event()

        def _stop(signum, frame):
            self.stdout.write("Stopping after the current cycle...")
            stop.set()

        previous = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, _stop)

        self.stdout.write(self.style.SUCCESS("Running one ingestion cycle." if options["once"] else "Ingestion worker running."))
        try:
            ok = run_forever(stop, interval=options["interval"], once=options["once"])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if options["once"] and not ok:
            # Non-zero exit, so a scheduled run that crashed shows as failed.
            raise CommandError("Ingestion cycle failed; see the traceback above.")
