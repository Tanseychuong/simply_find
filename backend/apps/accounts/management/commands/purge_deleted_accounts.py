"""Permanently delete accounts whose deletion hold has passed (see
apps/accounts/deletion.py). Safe to run often; runs from the ingest workflow."""

from django.core.management.base import BaseCommand

from apps.accounts.deletion import DELETION_HOLD, due_for_deletion, purge_due_accounts


class Command(BaseCommand):
    help = f"Delete accounts deactivated at the owner's request more than {DELETION_HOLD.days} days ago."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report how many are due.")

    def handle(self, *args, dry_run=False, **options):
        if dry_run:
            self.stdout.write(f"{due_for_deletion().count()} account(s) due for deletion.")
            return
        count = purge_due_accounts()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} account(s)."))
