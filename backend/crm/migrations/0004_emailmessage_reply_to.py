"""Add reply_to_email to CRM outbound messages."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0003_admin_russian_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailmessage",
            name="reply_to_email",
            field=models.EmailField(
                blank=True,
                default="",
                max_length=254,
                verbose_name="адрес для ответа",
            ),
        ),
    ]
