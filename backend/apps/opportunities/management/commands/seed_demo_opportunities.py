"""
Run via: python manage.py seed_demo_opportunities [--clear]

Fills the site with sample, already-approved listings so the landing page
(latest, closing soon, stats, category tiles) has something to show before
real submissions and fetched feeds arrive. The organisations are fictional
and the listings have no application URL, so nothing points visitors at a
real programme.

Dates are relative to when it runs: several listings were published in the
last week, and most have deadlines in the coming weeks. Safe to re-run —
listings that already exist (matched by title + organisation) are left
alone. --clear removes exactly these listings and nothing else; run it
before launch.

Needs the default categories (manage.py setup_categories).
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.opportunities.models import Opportunity, OpportunityCategory

# (field slug, role type, title, organisation, location, deadline in days or None,
#  published days ago, description)
DEMO_OPPORTUNITIES = [
    ("engineering-tech", "internship", "Software Engineering Intern (Summer 2027)", "Kestrel Digital",
     "Accra, Ghana (hybrid)", 12, 3.5,
     "Twelve-week paid internship on the product engineering team, building web and mobile features used "
     "by thousands of customers. Open to students in their penultimate or final year."),
    ("ngo-development", "internship", "Programme Support Intern", "Nile Partners for Development", "Juba, South Sudan",
     9, 2,
     "Six-month internship supporting field programmes in education and livelihoods: data collection, "
     "reporting and community meetings. Open to final-year students and graduates of the last two years."),
    ("business-finance", "graduate_programme", "Graduate Trainee Programme 2027", "Equator Commercial Bank",
     "Juba, South Sudan", 21, 4,
     "An 18-month rotation through retail banking, credit and operations, with classroom training and a "
     "mentor. For graduates in business, economics, finance or accounting."),
    ("engineering-tech", "entry_level", "Graduate Data Analyst", "Tamarind Analytics", "Kampala, Uganda", 21, 6,
     "Entry-level analyst role for recent graduates comfortable with SQL and spreadsheets. You'll build "
     "dashboards and reports for clients in retail and financial services, with structured training."),
    ("media-communications", "internship", "Product Design Internship", "Ember Studio", "Remote", 40, 9,
     "Six-month remote internship designing interfaces for early-stage startups. A portfolio of student or "
     "personal projects is required; experience with Figma is a plus."),
    ("business-finance", "entry_level", "Junior Operations Associate", "Harbour Logistics Group", "Tema, Ghana",
     None, 18,
     "Full-time graduate role supporting the operations team with scheduling, supplier coordination and "
     "process improvement. Applications are accepted until the position is filled."),
    ("health", "internship", "Public Health Research Intern", "Meridian Health Alliance", "Nairobi, Kenya", 14, 2.5,
     "Three-month internship on maternal health research: literature reviews, survey design and data "
     "cleaning. For students in public health, nursing, medicine or statistics."),
    ("agriculture-environment", "graduate_programme", "Agribusiness Graduate Fellowship Year", "Volta Farms",
     "Ho, Ghana", 33, 8,
     "A paid first year after university, working with smallholder farmers on supply and quality. Includes "
     "field training and a placement on a commercial farm."),
    ("education", "entry_level", "Assistant Teacher, Mathematics", "Bright Hill Academy", "Juba, South Sudan",
     6, 1,
     "Support lead teachers in secondary mathematics classes, run revision sessions and mark coursework. "
     "Recent graduates in mathematics or education are encouraged to apply."),
    ("law-government", "internship", "Legal Research Intern", "Centre for Justice and Governance", "Kigali, Rwanda",
     None, 13,
     "Part-time internship supporting legal research on land rights and access to justice. Law students in "
     "their third year or above may apply on a rolling basis."),
    ("education", "graduate_school", "Fully Funded MSc in Development Economics", "Lumen Institute of Technology",
     "Kigali, Rwanda", 47, 11,
     "A one-year master's for graduates of African universities, with tuition, accommodation and a stipend. "
     "Listed under Graduate school, not in the job feed."),
]


def _demo_q() -> Q:
    q = Q(pk__in=[])
    for _, _, title, organization, *_ in DEMO_OPPORTUNITIES:
        q |= Q(title=title, organization=organization)
    return q


class Command(BaseCommand):
    help = "Create sample approved opportunities for the landing page (--clear removes them)"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete the sample opportunities instead")

    def handle(self, *args, clear=False, **options):
        if clear:
            deleted, _ = Opportunity.objects.filter(_demo_q()).delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {deleted} sample row(s)."))
            return

        categories = OpportunityCategory.objects.in_bulk(field_name="slug")
        missing = {row[0] for row in DEMO_OPPORTUNITIES} - categories.keys()
        if missing:
            raise CommandError(f"Missing categories {sorted(missing)} — run `manage.py setup_categories` first.")

        admin = User.objects.filter(is_superuser=True).order_by("pk").first()
        now = timezone.now()
        end_of_today = now.replace(hour=23, minute=59, second=0, microsecond=0)
        created = 0

        with transaction.atomic():
            for slug, role_type, title, organization, location, deadline_days, days_ago, description in DEMO_OPPORTUNITIES:
                if Opportunity.objects.filter(title=title, organization=organization).exists():
                    continue
                published = now - timedelta(days=days_ago)
                opportunity = Opportunity.objects.create(
                    category=categories[slug],
                    role_type=role_type,
                    title=title,
                    organization=organization,
                    location=location,
                    description=description,
                    application_deadline=(
                        end_of_today + timedelta(days=deadline_days) if deadline_days is not None else None
                    ),
                    posted_by=admin,
                    source_type=Opportunity.SourceType.SUBMITTED,
                    status=Opportunity.Status.APPROVED,
                    reviewed_by=admin,
                    reviewed_at=published,
                    published_at=published,
                    # No URL to visit, so the enrichment worker has nothing to do.
                    enrichment_status=Opportunity.EnrichmentStatus.SKIPPED,
                    enrichment_checked_at=now,
                )
                # auto_now_add ignores values passed to create().
                Opportunity.objects.filter(pk=opportunity.pk).update(submitted_at=published - timedelta(hours=6))
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Sample opportunities ready — {created} created, {len(DEMO_OPPORTUNITIES) - created} already existed."
        ))
