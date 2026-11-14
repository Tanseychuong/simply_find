"""
Run via: python manage.py setup_fetch_sources [--dry-run]

Adds SimplyFind's starting list of feeds and company careers boards as
FetchSources. Safe to re-run: sources are matched by URL, existing ones
keep whatever an admin changed (interval, keywords, active flag), and only
missing ones are created. A source that breaks shows up as failing in
/admin/.

Why these:
  * Aggregator feeds that post internships and graduate programmes open to
    young Africans. They also post scholarships and senior jobs; the
    classifier (apps/ingestion/classify.py) keeps only student and
    recent-graduate roles.
  * Careers boards of employers with roles in Africa, read through the
    public job-board API of the ATS that hosts them. Only their
    internships, graduate and entry-level roles are kept.
  * Graduate school feeds, fetched weekly and OFF until an admin turns
    them on (graduate school listings are optional). Their URLs were not
    checked when this list was written: check each one's first fetch log.
"""

from django.core.management.base import BaseCommand

from apps.ingestion.models import FetchSource
from apps.opportunities.models import OpportunityCategory

RSS = FetchSource.ConnectorType.RSS
GREENHOUSE = FetchSource.ConnectorType.GREENHOUSE
ASHBY = FetchSource.ConnectorType.ASHBY
WORKABLE = FetchSource.ConnectorType.WORKABLE

AFRICA = (
    "Africa, Ghana, Accra, Kumasi, Nigeria, Lagos, Abuja, Kenya, Nairobi, Rwanda, Kigali, Uganda, Kampala, "
    "South Africa, Cape Town, Johannesburg, Côte d'Ivoire, Abidjan, Senegal, Dakar, Egypt, Cairo, Morocco, "
    "South Sudan, Juba, Sudan, Ethiopia, Tanzania, Zambia, Malawi, Burundi, DRC, Congo, Cameroon, Mozambique, Zimbabwe, Botswana"
)
AFRICA_OR_REMOTE = AFRICA + ", Remote"

WEEK = 7 * 24 * 60

# (name, connector, url, default field slug, role type, include_keywords, interval minutes, active)
SOURCES = [
    # --- Aggregator feeds (RSS), mixed: sorted per item ------------------------
    ("Opportunity Desk", RSS, "https://opportunitydesk.org/feed/", "other", "", "", 180, True),
    ("Opportunities for Africans", RSS, "https://www.opportunitiesforafricans.com/feed/", "other", "", "", 180, True),
    ("Opportunities for Youth", RSS, "https://opportunitiesforyouth.org/feed/", "other", "", "", 180, True),
    ("Opportunities Corners", RSS, "https://www.opportunitiescorners.com/feed/", "other", "", "", 360, True),
    ("ReliefWeb jobs", RSS, "https://reliefweb.int/jobs/rss.xml", "ngo-development", "", AFRICA, 360, True),
    ("JobWeb Ghana", RSS, "https://www.jobwebghana.com/feed/", "other", "", "", 360, True),
    # --- Company careers boards: only their entry-level roles are kept --------
    ("Moniepoint", GREENHOUSE, "https://job-boards.greenhouse.io/moniepoint", "business-finance", "", AFRICA, 720, True),
    ("Jumia", GREENHOUSE, "https://job-boards.eu.greenhouse.io/jumia", "business-finance", "", AFRICA, 720, True),
    ("Zipline", GREENHOUSE, "https://job-boards.greenhouse.io/flyzipline", "engineering-tech", "", AFRICA, 720, True),
    ("One Acre Fund", GREENHOUSE, "https://job-boards.greenhouse.io/oneacrefund", "agriculture-environment", "", "", 720, True),
    ("GiveDirectly", GREENHOUSE, "https://job-boards.greenhouse.io/givedirectly", "ngo-development", "", AFRICA_OR_REMOTE, 720, True),
    ("ALX Africa", GREENHOUSE, "https://job-boards.greenhouse.io/alxafrica", "education", "", "", 720, True),
    ("Teach For All", GREENHOUSE, "https://job-boards.greenhouse.io/teachforall", "education", "", AFRICA_OR_REMOTE, 720, True),
    ("Wikimedia Foundation", GREENHOUSE, "https://job-boards.greenhouse.io/wikimedia", "engineering-tech", "", AFRICA_OR_REMOTE, 720, True),
    # Not AFRICA_OR_REMOTE: Andela's remote roles are region-locked ("North America (Remote)").
    ("Andela", ASHBY, "https://jobs.ashbyhq.com/andela", "engineering-tech", "", AFRICA, 720, True),
    ("IDinsight", ASHBY, "https://jobs.ashbyhq.com/idinsight", "ngo-development", "", AFRICA, 720, True),
    ("Kuda", WORKABLE, "https://apply.workable.com/kuda/", "business-finance", "", "", 720, True),
    ("FairMoney", WORKABLE, "https://apply.workable.com/fairmoney/", "business-finance", "", "", 720, True),
    ("Helium Health", WORKABLE, "https://apply.workable.com/helium-health/", "health", "", "", 720, True),
    # --- Graduate school (optional, weekly, off until turned on) --------------
    ("Opportunity Desk: graduate study", RSS, "https://opportunitydesk.org/category/scholarships/feed/",
     "education", "graduate_school", "", WEEK, False),
    ("Opportunities for Africans: graduate study", RSS,
     "https://www.opportunitiesforafricans.com/category/scholarships/feed/", "education", "graduate_school", "", WEEK, False),
]


class Command(BaseCommand):
    help = "Create SimplyFind's starting feeds and careers boards as FetchSources (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created, change nothing")

    def handle(self, *args, dry_run=False, **options):
        categories = {c.slug: c for c in OpportunityCategory.objects.all()}
        created = 0
        for name, connector, url, slug, role_type, keywords, interval, active in SOURCES:
            if FetchSource.objects.filter(url=url).exists():
                self.stdout.write(f"  exists   {name}")
                continue
            category = categories.get(slug)
            if category is None:
                self.stdout.write(self.style.WARNING(f"  skipped  {name}: no '{slug}' category (run setup_categories)"))
                continue
            if not dry_run:
                FetchSource.objects.create(
                    name=name, connector_type=connector, url=url, category=category, role_type=role_type,
                    include_keywords=keywords, fetch_interval_minutes=interval, is_active=active,
                )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"  {'would add' if dry_run else 'added'}    {name}"))
        self.stdout.write(f"{created} source(s) {'to add' if dry_run else 'added'}.")
