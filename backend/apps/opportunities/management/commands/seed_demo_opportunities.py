"""
Run via: python manage.py seed_demo_opportunities [--clear]

Fills the site with sample, already-approved listings so the landing page
(latest, closing soon, stats, category tiles) has something to show before
real submissions and fetched feeds arrive. The organisations are fictional
and the listings have no application URL, so nothing points visitors at a
real programme.

Dates are relative to when it runs: every listing is past its free-access
time (visible to anonymous visitors), several were published in the last
week, and most have deadlines in the coming weeks. Safe to re-run —
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

# (category slug, title, organisation, location, deadline in days or None,
#  published days ago, description)
DEMO_OPPORTUNITIES = [
    ("scholarships", "Undergraduate STEM Scholarship 2027", "Savanna Futures Foundation", "Accra, Ghana", 9, 3,
     "Full tuition and a monthly stipend for first-year students admitted to a science, technology, "
     "engineering or mathematics degree at an accredited African university. Applicants need strong "
     "secondary-school results and a short essay on a problem they want to solve in their community."),
    ("scholarships", "Women in Engineering Master's Award", "Northbridge Education Trust", "Remote — any country", 26, 5,
     "Covers tuition for a one- or two-year master's in any engineering discipline, plus mentoring from "
     "practising engineers. Open to women graduates with at least a second-class upper degree."),
    ("scholarships", "Pan-African Graduate Study Bursary", "Baobab Scholars Fund", "Nairobi, Kenya", 47, 11,
     "Partial bursaries for postgraduate study at universities across the continent. Priority goes to "
     "applicants who plan to work in the public sector or education after graduating."),
    ("scholarships", "Computer Science Merit Scholarship", "Lumen Institute of Technology", "Kigali, Rwanda", None, 16,
     "Renewable merit scholarship for undergraduate computer science students. Applications are reviewed "
     "on a rolling basis throughout the academic year."),
    ("fellowships", "Emerging Leaders Fellowship", "Horizon Civic Institute", "Johannesburg, South Africa", 14, 2.5,
     "A nine-month, part-time leadership programme for early-career professionals under 30. Fellows join "
     "monthly workshops, are paired with a mentor and deliver a community project by the end of the cohort."),
    ("fellowships", "Climate Research Fellowship", "Volta Climate Collective", "Ho, Ghana", 33, 8,
     "Funded twelve-month research fellowship on climate adaptation in West African agriculture. Includes "
     "a research budget, field travel and supervision from senior scientists."),
    ("fellowships", "Public Health Policy Fellowship", "Meridian Health Alliance", "Remote", None, 13,
     "Six-month remote fellowship placing recent graduates with health ministries and NGOs to work on "
     "policy research. A monthly stipend is provided."),
    ("fellowships", "Journalism & Data Storytelling Fellowship", "Openline Media Lab", "Lagos, Nigeria", 6, 4,
     "For young journalists who want to report with data. Fellows spend three months in the newsroom, "
     "learn data analysis and visualisation, and publish an investigative story."),
    ("jobs", "Software Engineering Intern (Summer 2027)", "Kestrel Digital", "Accra, Ghana (hybrid)", 12, 3.5,
     "Twelve-week paid internship on the product engineering team, building web and mobile features used "
     "by thousands of customers. Open to students in their penultimate or final year."),
    ("jobs", "Graduate Data Analyst", "Tamarind Analytics", "Kampala, Uganda", 21, 6,
     "Entry-level analyst role for recent graduates comfortable with SQL and spreadsheets. You'll build "
     "dashboards and reports for clients in retail and financial services, with structured training."),
    ("jobs", "Product Design Internship", "Ember Studio", "Remote", 40, 9,
     "Six-month remote internship designing interfaces for early-stage startups. A portfolio of student or "
     "personal projects is required; experience with Figma is a plus."),
    ("jobs", "Junior Operations Associate", "Harbour Logistics Group", "Tema, Ghana", None, 18,
     "Full-time graduate role supporting the operations team with scheduling, supplier coordination and "
     "process improvement. Applications are accepted until the position is filled."),
    ("grants", "Student Venture Seed Grant", "Sunrise Venture Fund", "Kumasi, Ghana", 18, 2.2,
     "Non-equity grants for student-led startups at the idea or prototype stage, with a six-week "
     "incubation programme and pitch day at the end."),
    ("grants", "Community Water Project Grant", "Clearwater Communities Fund", "West Africa", 55, 10,
     "Funding for community-led projects that improve access to clean water and sanitation. Student "
     "societies and registered community groups may apply."),
    ("grants", "Early-Career Research Travel Grant", "Atlas Research Council", "Remote — any country", 28, 20,
     "Covers travel and registration for early-career researchers presenting their work at an "
     "international conference in the coming year."),
]


def _demo_q() -> Q:
    q = Q(pk__in=[])
    for _, title, organization, *_ in DEMO_OPPORTUNITIES:
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
            for slug, title, organization, location, deadline_days, days_ago, description in DEMO_OPPORTUNITIES:
                if Opportunity.objects.filter(title=title, organization=organization).exists():
                    continue
                published = now - timedelta(days=days_ago)
                opportunity = Opportunity.objects.create(
                    category=categories[slug],
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
