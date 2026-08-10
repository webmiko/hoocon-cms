# Generated manually for SKU.first_published_at (Новинки).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0013_sku_stock_qty"),
    ]

    operations = [
        migrations.AddField(
            model_name="sku",
            name="first_published_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                default=None,
                help_text=(
                    "Когда SKU впервые стал виден в публичном каталоге. "
                    "Окно «Новое» — 30 суток; не путать с created_at / updated_at ETL."
                ),
                null=True,
                verbose_name="впервые на сайте",
            ),
        ),
    ]
