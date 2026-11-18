"""Allow one foreign article to cover several own SKUs.

A single Belimo article legitimately replaces more than one Hoocon model
(``NM24A-S2`` covers both 6 Nm and 8 Nm classes), so uniqueness moves to
``(brand, foreign_code_key, sku)``. ``resolve_position_code`` already
refuses multi-row matches, keeping the ЛК-10 picker safe.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0022_stock_snapshot"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="analogmap",
            name="catalog_analogmap_brand_code_uniq",
        ),
        migrations.AddConstraint(
            model_name="analogmap",
            constraint=models.UniqueConstraint(
                fields=("brand", "foreign_code_key", "sku"),
                name="catalog_analogmap_brand_code_sku_uniq",
            ),
        ),
    ]
