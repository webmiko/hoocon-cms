"""Rename SiteSettings Admin labels to «интеграции»."""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    """AlterModelOptions only — no schema change."""

    dependencies = [
        ("sitesettings", "0006_fill_analytics_counter_ids"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="sitesettings",
            options={
                "verbose_name": "интеграция",
                "verbose_name_plural": "интеграции",
            },
        ),
    ]
