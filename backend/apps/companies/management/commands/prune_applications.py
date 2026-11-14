"""
Delete old applications (answers and uploaded files) once the retention
period has passed:

  * applications to jobs whose deadline passed more than N days ago, and
  * withdrawn applications older than N days.

N is settings.APPLICATION_RETENTION_DAYS (env APPLICATION_RETENTION_DAYS).
It is unset by default, which means *keep*: choosing a period is a legal /
policy decision, and the Privacy notice must say the same thing. Once set,
schedule this alongside prune_visitor_data.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Application


class Command(BaseCommand):
    help = "Delete applications older than APPLICATION_RETENTION_DAYS (does nothing while it is unset)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be deleted.")

    def handle(self, *args, dry_run=False, **options):
        days = settings.APPLICATION_RETENTION_DAYS
        if not days:
            self.stdout.write("APPLICATION_RETENTION_DAYS is not set; keeping all applications.")
            return
        cutoff = timezone.now() - timedelta(days=days)
        old = Application.objects.filter(
            Q(opportunity__application_deadline__lt=cutoff)
            | Q(status=Application.Status.WITHDRAWN, updated_at__lt=cutoff)
        )
        count = old.count()
        if dry_run:
            self.stdout.write(f"Would delete {count} application(s) older than {days} days.")
            return
        for application in old.iterator():
            application.delete()  # answers cascade; signals.py removes their files
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} application(s) older than {days} days."))
