# Generated manually for StaffVkProfile.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_alter_staffmailbox_folder_help"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffVkProfile",
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
                    "vk_user_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Числовой id из лички с сообществом. Клиент пишет /chatid — бот вернёт id для Admin.",
                        max_length=64,
                        verbose_name="ID пользователя VK",
                    ),
                ),
                (
                    "vk_alerts_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Выкл — не слать личные уведомления этому сотруднику во VK.",
                        verbose_name="уведомления VK включены",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vk_profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "VK сотрудника",
                "verbose_name_plural": "VK сотрудников",
            },
        ),
    ]
