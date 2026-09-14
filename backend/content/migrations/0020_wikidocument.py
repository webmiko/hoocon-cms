# Generated manually for staff Wiki pages.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0019_reschedule_p2_weekly_mondays"),
    ]

    operations = [
        migrations.CreateModel(
            name="WikiDocument",
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
                ("title", models.CharField(max_length=300, verbose_name="заголовок")),
                (
                    "slug",
                    models.SlugField(
                        db_index=True,
                        max_length=300,
                        unique=True,
                        verbose_name="сегмент URL",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="Общее",
                        max_length=100,
                        verbose_name="категория",
                    ),
                ),
                (
                    "summary",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Пояснение для списка: что за цифрами и зачем документ.",
                        verbose_name="краткое описание",
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Полный HTML-документ или фрагмент. Только для сотрудников в админке.",
                        verbose_name="HTML",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        db_index=True,
                        default=0,
                        verbose_name="порядок",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="активна",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="создано"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="обновлено"),
                ),
            ],
            options={
                "verbose_name": "страница вики",
                "verbose_name_plural": "вики",
                "ordering": ("category", "sort_order", "title"),
            },
        ),
    ]
