"""
Run via: python manage.py setup_categories

Creates the starter opportunity categories so a fresh database can accept
submissions straight away. Safe to re-run: existing categories (matched by
slug) are left exactly as an admin last edited them, and categories added
in /admin/ are never touched. Runs on every deploy from the Procfile's
release step.
"""

from django.core.management.base import BaseCommand

from apps.opportunities.models import OpportunityCategory

DEFAULT_CATEGORIES = [
    ("scholarships", "Scholarships", "Funding for undergraduate and graduate study."),
    ("fellowships", "Fellowships", "Leadership, research and professional fellowship programmes."),
    ("jobs", "Jobs & Internships", "Full-time roles, internships and graduate schemes."),
    ("grants", "Grants", "Funding for projects, ventures and community initiatives."),
]


class Command(BaseCommand):
    help = "Create the starter opportunity categories if they don't exist yet"

    def handle(self, *args, **options):
        created = 0
        for slug, name, description in DEFAULT_CATEGORIES:
            _, was_created = OpportunityCategory.objects.get_or_create(
                slug=slug, defaults={"name": name, "description": description},
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Categories ready — {created} created, {len(DEFAULT_CATEGORIES) - created} already existed."
        ))
