"""
Run via: python manage.py setup_fetch_sources [--dry-run]

Adds EEL's researched list of opportunity feeds and company careers boards
as FetchSources. Safe to re-run: sources are matched by URL, existing ones
keep whatever an admin changed (interval, keywords, active flag), and only
missing ones are created. Every URL here was checked to return listings
(October 2026); a source that later breaks shows up as failing in /admin/.

Why these:
  * Opportunity aggregators that cover scholarships, fellowships, grants and
    jobs open to young Africans — their items are filed into the right
    category per item (apps/ingestion/classify.py).
  * Careers boards of employers with real roles in Africa, read through the
    public job-board API of the ATS that hosts them. Global employers get
    include_keywords so only their Africa-based or remote roles come in.
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
    "Ethiopia, Tanzania, Zambia, Malawi, Burundi, DRC, Congo, Cameroon, Mozambique, Zimbabwe, Botswana"
)
AFRICA_OR_REMOTE = AFRICA + ", Remote"
YOUTH = "Africa, African, youth, young, student, graduate, women, girls, emerging, early-career, developing countries"

# (name, connector, url, default category slug, include_keywords, interval minutes)
SOURCES = [
    # --- Opportunity platforms (RSS) -----------------------------------------
    ("Opportunity Desk", RSS, "https://opportunitydesk.org/feed/", "fellowships", "", 180),
    ("Opportunities for Africans", RSS, "https://www.opportunitiesforafricans.com/feed/", "fellowships", "", 180),
    ("Opportunities for Youth", RSS, "https://opportunitiesforyouth.org/feed/", "fellowships", "", 180),
    ("Opportunities Corners", RSS, "https://www.opportunitiescorners.com/feed/", "fellowships", "", 360),
    ("Funds for NGOs", RSS, "https://www.fundsforngos.org/feed/", "grants", YOUTH, 360),
    ("ReliefWeb jobs", RSS, "https://reliefweb.int/jobs/rss.xml", "jobs", AFRICA, 360),
    ("JobWeb Ghana", RSS, "https://www.jobwebghana.com/feed/", "jobs", "", 360),
    # --- Company careers boards ----------------------------------------------
    ("Moniepoint", GREENHOUSE, "https://job-boards.greenhouse.io/moniepoint", "jobs", AFRICA, 720),
    ("Jumia", GREENHOUSE, "https://job-boards.eu.greenhouse.io/jumia", "jobs", AFRICA, 720),
    ("Zipline", GREENHOUSE, "https://job-boards.greenhouse.io/flyzipline", "jobs", AFRICA, 720),
    ("One Acre Fund", GREENHOUSE, "https://job-boards.greenhouse.io/oneacrefund", "jobs", "", 720),
    ("GiveDirectly", GREENHOUSE, "https://job-boards.greenhouse.io/givedirectly", "jobs", AFRICA_OR_REMOTE, 720),
    ("ALX Africa", GREENHOUSE, "https://job-boards.greenhouse.io/alxafrica", "jobs", "", 720),
    ("Teach For All", GREENHOUSE, "https://job-boards.greenhouse.io/teachforall", "jobs", AFRICA_OR_REMOTE, 720),
    ("Wikimedia Foundation", GREENHOUSE, "https://job-boards.greenhouse.io/wikimedia", "jobs", AFRICA_OR_REMOTE, 720),
    # Not AFRICA_OR_REMOTE: Andela's remote roles are region-locked ("North America (Remote)").
    ("Andela", ASHBY, "https://jobs.ashbyhq.com/andela", "jobs", AFRICA, 720),
    ("IDinsight", ASHBY, "https://jobs.ashbyhq.com/idinsight", "jobs", AFRICA, 720),
    ("Kuda", WORKABLE, "https://apply.workable.com/kuda/", "jobs", "", 720),
    ("FairMoney", WORKABLE, "https://apply.workable.com/fairmoney/", "jobs", "", 720),
    ("Helium Health", WORKABLE, "https://apply.workable.com/helium-health/", "jobs", "", 720),
]


class Command(BaseCommand):
    help = "Create EEL's researched opportunity feeds and careers boards as FetchSources (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created, change nothing")

    def handle(self, *args, dry_run=False, **options):
        categories = {c.slug: c for c in OpportunityCategory.objects.all()}
        created = 0
        for name, connector, url, slug, keywords, interval in SOURCES:
            if FetchSource.objects.filter(url=url).exists():
                self.stdout.write(f"  exists   {name}")
                continue
            category = categories.get(slug)
            if category is None:
                self.stdout.write(self.style.WARNING(f"  skipped  {name}: no '{slug}' category (run setup_categories)"))
                continue
            if not dry_run:
                FetchSource.objects.create(
                    name=name, connector_type=connector, url=url, category=category,
                    include_keywords=keywords, fetch_interval_minutes=interval,
                )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"  {'would add' if dry_run else 'added'}    {name}"))
        self.stdout.write(f"{created} source(s) {'to add' if dry_run else 'added'}.")
