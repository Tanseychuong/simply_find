"""
Data fix for listings fetched before the RSS connector was corrected.

The old connector stored each item's RSS pubDate (when the source
published it) in `application_deadline`. Feeds never carried a real
deadline, so for fetched rows that value is always a publish date — and
with the feed now hiding listings whose deadline has passed, every one of
those rows would disappear. Move it to `source_published_at` instead.

User-submitted listings are untouched: their deadlines were typed in by a
person and are real.
"""

from django.db import migrations
from django.db.models import F


def move_pubdate(apps, schema_editor):
    Opportunity = apps.get_model("opportunities", "Opportunity")
    Opportunity.objects.filter(
        source_type="fetched",
        source_published_at__isnull=True,
        application_deadline__isnull=False,
    ).update(source_published_at=F("application_deadline"), application_deadline=None)


class Migration(migrations.Migration):

    dependencies = [
        ("opportunities", "0003_opportunity_enrichment"),
    ]

    operations = [
        migrations.RunPython(move_pubdate, migrations.RunPython.noop),
    ]
