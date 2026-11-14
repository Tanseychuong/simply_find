"""
Adds Opportunity.listing_url and backfills it for listings already fetched
from RSS feeds. Those feeds are aggregators, so the stored link is the
aggregator's article; marking the rows for enrichment again lets the
worker swap in the organiser's own link (apps/ingestion/organizer.py).

Their organisation is cleared too: it held the post's author
(<dc:creator>, e.g. "Jude Ogar") or the aggregator's site name, never the
organiser. Enrichment refills it from the organiser's site.
"""

from django.db import migrations, models
from django.db.models import F


def backfill_listing_url(apps, schema_editor):
    Opportunity = apps.get_model("opportunities", "Opportunity")
    Opportunity.objects.filter(
        source_type="fetched",
        fetch_source__connector_type="rss",
        listing_url="",
    ).exclude(opportunity_url="").update(
        listing_url=F("opportunity_url"),
        organization="",
        enrichment_status="pending",
        enrichment_attempts=0,
        enrichment_checked_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0004_fetchsource_job_boards_and_keywords"),
        ("opportunities", "0004_move_fetched_pubdate_out_of_deadline"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunity",
            name="listing_url",
            field=models.URLField(blank=True, db_index=True, max_length=500),
        ),
        migrations.RunPython(backfill_listing_url, migrations.RunPython.noop),
    ]
