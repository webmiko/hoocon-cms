"""Sync SKU.analog_belimo_code to the confirmed Belimo AnalogMap article.

The field is a cache. SEO and search no longer read it, but admin search
and older rows still do. An unconfirmed code is cleared; a confirmed pair
is copied from the first active Belimo row (same order as
belimo_article_for_sku: torque, then article).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.apps.registry import Apps
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def _confirmed_belimo_code(sku: object) -> str:
    rows = [
        row
        for row in sku.analog_maps.all()  # type: ignore[attr-defined]
        if row.is_active and (row.brand or "").casefold() == "belimo"
    ]
    rows.sort(key=lambda row: (row.torque_nm or 0, row.foreign_code or ""))
    if not rows:
        return ""
    return (rows[0].foreign_code or "").strip()


def forwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    SKU = apps.get_model("catalog", "SKU")
    for sku in SKU.objects.prefetch_related("analog_maps"):
        confirmed = _confirmed_belimo_code(sku)
        current = (sku.analog_belimo_code or "").strip()
        if current == confirmed:
            continue
        SKU.objects.filter(pk=sku.pk).update(analog_belimo_code=confirmed)


def backwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Stored codes are a cache; the previous values are not recoverable."""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0025_analogmap_belimo_fu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
