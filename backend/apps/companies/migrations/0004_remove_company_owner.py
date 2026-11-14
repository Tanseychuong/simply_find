"""Drop Company.owner, now that 0003 copied it into memberships. Separate
from 0003 because PostgreSQL refuses an ALTER TABLE in the same transaction
as the data update ("cannot ALTER TABLE because it has pending trigger events")."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0003_company_teams'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='company',
            name='owner',
        ),
    ]
