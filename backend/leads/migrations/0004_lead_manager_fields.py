"""Add Lead assignee / processed_by / processed_at for manager tracking."""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Manager ownership fields on Lead."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("leads", "0003_lead_seen_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="assignee",
            field=models.ForeignKey(
                blank=True,
                help_text="Менеджер, который сейчас ведёт заявку.",
                limit_choices_to={"is_staff": True},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_leads",
                to=settings.AUTH_USER_MODEL,
                verbose_name="в работе у",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="processed_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Менеджер, который завершил обработку заявки.",
                limit_choices_to={"is_staff": True},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="processed_leads",
                to=settings.AUTH_USER_MODEL,
                verbose_name="обработал",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="processed_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Когда заявка была завершена (status=done).",
                null=True,
                verbose_name="обработано",
            ),
        ),
    ]
