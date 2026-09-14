"""Staff MAX profile for personal manager alerts."""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_staff_notification_labels_ru"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffMaxProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "max_user_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text=(
                            "Числовой user_id из личного чата с ботом. "
                            "В боте отправьте /chatid и скопируйте ответ сюда."
                        ),
                        max_length=64,
                        verbose_name="user_id в MAX",
                    ),
                ),
                (
                    "max_alerts_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Выкл — не слать личные уведомления этому сотруднику.",
                        verbose_name="уведомления в MAX включены",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="max_profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "MAX сотрудника",
                "verbose_name_plural": "MAX сотрудников",
            },
        ),
    ]
