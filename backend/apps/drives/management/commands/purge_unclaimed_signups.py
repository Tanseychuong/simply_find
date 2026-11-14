from django.core.management.base import BaseCommand

from apps.drives.services import purge_unclaimed


class Command(BaseCommand):
    help = "Delete accounts made at a recruitment drive desk that were never claimed (run daily)."

    def handle(self, *args, **options):
        self.stdout.write(f"Deleted {purge_unclaimed()} unclaimed account(s).")
