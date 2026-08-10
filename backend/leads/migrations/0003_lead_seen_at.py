"""Add Lead.seen_at for admin sticker (unread) tracking."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    """Lead.seen_at — null means unread for the header sticker."""

    dependencies = [
        ("leads", "0002_crm_client_and_mail"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="seen_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "Когда менеджер открыл заявку в Admin "
                    "(стикер считает непросмотренные)."
                ),
                null=True,
                verbose_name="просмотрено",
            ),
        ),
    ]
