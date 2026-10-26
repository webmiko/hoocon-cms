# Generated manually for quote ↔ email CRM thread.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0022_quote_price_includes_vat"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailmessage",
            name="quote",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="emails",
                to="crm.quote",
                verbose_name="коммерческое предложение",
            ),
        ),
    ]
