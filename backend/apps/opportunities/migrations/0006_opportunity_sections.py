"""
Adds Opportunity.sections — the description split into named sections
(About the organisation, Eligibility, Benefits, How to apply …).

Fetched listings are queued for enrichment again so the worker can read
the sections from their pages; job-board rows also get theirs on the next
fetch of their board (services.fetch_source fills blank sections on items
it already has). User-submitted listings keep their plain description.
"""

from django.db import migrations, models


def requeue_fetched(apps, schema_editor):
    Opportunity = apps.get_model("opportunities", "Opportunity")
    Opportunity.objects.filter(source_type="fetched").exclude(opportunity_url="").update(
        enrichment_status="pending",
        enrichment_attempts=0,
        enrichment_checked_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("opportunities", "0005_opportunity_listing_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunity",
            name="sections",
            field=models.JSONField(
                blank=True, default=list,
                help_text='List of {"kind", "title", "blocks": [{"type": "p"|"li"|"h", "text"}]}. '
                          "Kinds: overview, organization, eligibility, responsibilities, benefits, documents, "
                          "how_to_apply, dates, other.",
            ),
        ),
        migrations.RunPython(requeue_fetched, migrations.RunPython.noop),
    ]
