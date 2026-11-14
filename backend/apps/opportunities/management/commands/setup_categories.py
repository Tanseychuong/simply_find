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

# Fields of work. The kind of role (internship, graduate programme,
# entry-level, graduate school) is Opportunity.role_type, not a category.
DEFAULT_CATEGORIES = [
    ("engineering-tech", "Engineering & Technology", "Software, IT, data, and engineering."),
    ("business-finance", "Business & Finance", "Accounting, banking, consulting, sales and operations."),
    ("ngo-development", "NGOs & Development", "Humanitarian, development and international organisations."),
    ("health", "Health", "Clinical, public health and pharmacy."),
    ("education", "Education & Research", "Teaching, research and academic support."),
    ("agriculture-environment", "Agriculture & Environment", "Farming, food security, climate and natural resources."),
    ("law-government", "Law & Government", "Legal, policy and public service."),
    ("media-communications", "Media & Communications", "Journalism, marketing, design and communications."),
    ("other", "Other fields", "Roles that don't fit the fields above."),
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
