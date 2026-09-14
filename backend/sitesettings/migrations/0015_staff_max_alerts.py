"""SiteSettings flags for staff MAX DM alerts."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sitesettings", "0014_staff_notification_labels_ru"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="staff_max_leads_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Личные сообщения бота при новой заявке (RFQ / консультация / "
                    "замена). Нужен user_id в карточке сотрудника (/chatid в боте)."
                ),
                verbose_name="MAX при новой заявке",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="staff_max_support_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Входящее сообщение в чат поддержки → личный MAX менеджерам "
                    "с привязанным user_id."
                ),
                verbose_name="MAX при сообщении в поддержке",
            ),
        ),
    ]
