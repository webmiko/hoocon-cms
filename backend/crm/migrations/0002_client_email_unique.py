"""Normalize Client.email and enforce uniqueness (audit P0-3)."""

from __future__ import annotations

from django.db import migrations, models


def _normalize_and_dedupe_emails(apps, schema_editor) -> None:  # noqa: ARG001
    """Lowercase emails; merge duplicate clients onto the oldest row."""
    Client = apps.get_model("crm", "Client")
    Lead = apps.get_model("leads", "Lead")
    Activity = apps.get_model("crm", "Activity")
    EmailMessage = apps.get_model("crm", "EmailMessage")

    seen: dict[str, int] = {}
    for client in Client.objects.order_by("pk").iterator():
        email = (client.email or "").strip().lower()
        if not email:
            email = f"missing-{client.pk}@invalid.local"
        if email != client.email:
            client.email = email
            client.save(update_fields=["email"])
        if email not in seen:
            seen[email] = client.pk
            continue
        keep_id = seen[email]
        Lead.objects.filter(client_id=client.pk).update(client_id=keep_id)
        Activity.objects.filter(client_id=client.pk).update(client_id=keep_id)
        EmailMessage.objects.filter(client_id=client.pk).update(client_id=keep_id)
        client.delete()


class Migration(migrations.Migration):
    """Unique normalized Client.email."""

    dependencies = [
        ("crm", "0001_crm_client_and_mail"),
        ("leads", "0004_lead_manager_fields"),
    ]

    operations = [
        migrations.RunPython(_normalize_and_dedupe_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="client",
            name="email",
            field=models.EmailField(
                db_index=True,
                help_text="Уникальный ключ карточки (нормализуется в нижний регистр).",
                max_length=254,
                unique=True,
                verbose_name="email",
            ),
        ),
        migrations.AlterField(
            model_name="emailmessage",
            name="body",
            field=models.TextField(
                help_text="До 20 000 символов.",
                max_length=20000,
                verbose_name="текст письма",
            ),
        ),
    ]
