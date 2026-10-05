"""Add Client.company_key (normalized company match key) + backfill."""

from __future__ import annotations

from django.db import migrations, models


def _normalize_company_key(raw: str) -> str:
    """Snapshot of leads.services.normalize_company_label.

    Copied into the migration on purpose: the runtime helper may evolve,
    but backfill must stay reproducible (casefold + collapse spaces +
    strip quotes).
    """
    text = " ".join((raw or "").split()).casefold()
    for ch in "«»\"'":
        text = text.replace(ch, "")
    return " ".join(text.split())


def backfill_company_key(apps, schema_editor) -> None:
    """Fill company_key for existing clients (one update per row)."""
    client_model = apps.get_model("crm", "Client")
    for client in client_model.objects.exclude(company="").iterator():
        key = _normalize_company_key(client.company)
        if client.company_key != key:
            client.company_key = key
            client.save(update_fields=["company_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0004_emailmessage_reply_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="company_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                editable=False,
                help_text=(
                    "Нормализованный ключ совпадения компании (как у "
                    "закреплённых правил менеджеров). Заполняется автоматически."
                ),
                max_length=200,
                verbose_name="ключ компании",
            ),
        ),
        migrations.RunPython(backfill_company_key, migrations.RunPython.noop),
    ]
