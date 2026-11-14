from django.core.management.base import BaseCommand

from apps.analytics.services import prune_old_data


class Command(BaseCommand):
    help = "Erase old IP addresses and delete old page views and visitors, as promised in the privacy notice."

    def handle(self, *args, **options):
        views, visitors = prune_old_data()
        self.stdout.write(f"Deleted {views} page views and {visitors} inactive visitors.")
