"""LeadItem lines + RFQ soft-bundle fields; backfill items from legacy sku."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def _backfill_items(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Create LeadItem from existing Lead.sku when present."""
    Lead = apps.get_model("leads", "Lead")
    LeadItem = apps.get_model("leads", "LeadItem")
    for lead in Lead.objects.exclude(sku_id=None).iterator():
        if LeadItem.objects.filter(lead_id=lead.pk).exists():
            continue
        sku = lead.sku
        code = getattr(sku, "sku_code", "") or ""
        LeadItem.objects.create(
            lead_id=lead.pk,
            sku_id=lead.sku_id,
            sku_code=code,
            quantity=lead.quantity or 1,
            sort_order=0,
        )


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep items on reverse (schema drop removes them)."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_productimage_image_card"),
        ("leads", "0007_admin_ru_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="rfq_bundle_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Нормализованные компания|имя для мягкой группировки RFQ.",
                max_length=400,
                verbose_name="ключ нити КП",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="rfq_bundle_root",
            field=models.ForeignKey(
                blank=True,
                help_text="Первая открытая заявка нити; у корня пусто.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rfq_bundle_children",
                to="leads.lead",
                verbose_name="корень нити КП",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="company",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Для запроса КП обязательна: ключ нити КП = компания + имя.",
                max_length=200,
                verbose_name="компания",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="quantity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Сводка: количество по первому артикулу (RFQ).",
                null=True,
                verbose_name="количество",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="sku",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Сводка: первый артикул из позиций (необязательно; "
                    "при удалении артикула связь обнуляется)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leads",
                to="catalog.sku",
                verbose_name="артикул (SKU)",
            ),
        ),
        migrations.CreateModel(
            name="LeadItem",
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
                    "sku_code",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Снимок кода на момент заявки "
                            "(если SKU сняли с публикации)."
                        ),
                        max_length=100,
                        verbose_name="код артикула",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(default=1, verbose_name="количество"),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(default=0, verbose_name="порядок"),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="leads.lead",
                        verbose_name="заявка",
                    ),
                ),
                (
                    "sku",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lead_items",
                        to="catalog.sku",
                        verbose_name="артикул (SKU)",
                    ),
                ),
            ],
            options={
                "verbose_name": "позиция заявки",
                "verbose_name_plural": "позиции заявки",
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.RunPython(_backfill_items, _noop_reverse),
    ]
