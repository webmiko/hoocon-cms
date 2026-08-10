"""Fix company page warranty wording: 3 years → 24 months."""

from __future__ import annotations

from django.db import migrations

# Keep in sync with config.warranty.WARRANTY_COMPANY_LI (WARRANTY_MONTHS=24).
_NEW = "Гарантия 24 месяца на приводы линейки."
_OLD = "Гарантия 3 года на приводы линейки."
_OLD_ALT = "Гарантия три года на приводы линейки."


def _fix_company_warranty(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Replace outdated 3-year warranty line on the company Page."""
    Page = apps.get_model("content", "Page")
    page = Page.objects.filter(slug="company").first()
    if page is None or not page.body:
        return
    body = page.body
    for old in (_OLD, _OLD_ALT):
        if old in body:
            body = body.replace(old, _NEW)
    if body != page.body:
        page.body = body
        page.save(update_fields=["body", "updated_at"])


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Do not restore the incorrect 3-year wording on reverse."""
    return


class Migration(migrations.Migration):
    """Data: company page warranty is 24 months (canonical)."""

    dependencies = [
        ("content", "0010_news_launch_h8205_lav"),
    ]

    operations = [
        migrations.RunPython(_fix_company_warranty, _noop_reverse),
    ]
