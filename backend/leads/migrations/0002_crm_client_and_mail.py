# Generated manually for CRM Lead.client link.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0001_crm_client_and_mail"),
        ("leads", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="client",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Карточка клиента в CRM "
                    "(создаётся автоматически при новой заявке)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leads",
                to="crm.client",
                verbose_name="клиент CRM",
            ),
        ),
    ]
