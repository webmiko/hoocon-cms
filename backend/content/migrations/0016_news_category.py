"""Add NewsCategory and assign existing news to rubrics."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models

# Keep in sync with content.news_categories (historical models cannot import it).
_DEFAULT_CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("produkty", "Продукты", 10),
    ("stati", "Статьи", 20),
    ("meropriyatiya", "Мероприятия", 30),
    ("kompaniya", "Компания", 40),
)

_NEWS_SLUG_TO_CATEGORY: dict[str, str] = {
    "launch-hva-5nm": "produkty",
    "launch-h8205-lav": "produkty",
    "launch-br-adapters": "produkty",
    "articles-podbor-i-sertifikaty": "stati",
    "aquatherm-2025": "meropriyatiya",
    "mirklimata-2025": "meropriyatiya",
    "mir-klimata-2026-hoocon": "meropriyatiya",
    "hoocon-airvent-2026": "meropriyatiya",
    "partner-snizhenie-cen-022026": "kompaniya",
}


def _category_slug_for_news(news_slug: str) -> str:
    if news_slug.startswith("article-"):
        return "stati"
    return _NEWS_SLUG_TO_CATEGORY.get(news_slug, "kompaniya")


def _seed_and_assign(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Create four categories and assign every existing news row."""
    NewsCategory = apps.get_model("content", "NewsCategory")
    News = apps.get_model("content", "News")
    by_slug: dict[str, object] = {}
    for slug, name, sort_order in _DEFAULT_CATEGORIES:
        obj, _ = NewsCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "is_published": True,
            },
        )
        by_slug[slug] = obj
    for news in News.objects.all().only("id", "slug", "category_id"):
        target = by_slug.get(_category_slug_for_news(news.slug))
        if target is None:
            continue
        if news.category_id == target.pk:
            continue
        news.category = target
        # Match content.news_categories.assign_news_categories: bump updated_at
        # (auto_now only refreshes when the field is in update_fields).
        news.save(update_fields=["category", "updated_at"])


def _clear_categories(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Detach FK and delete seeded categories on reverse."""
    NewsCategory = apps.get_model("content", "NewsCategory")
    News = apps.get_model("content", "News")
    News.objects.update(category=None)
    NewsCategory.objects.filter(
        slug__in=[slug for slug, _, _ in _DEFAULT_CATEGORIES],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0015_periodic_publish_due_articles"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsCategory",
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
                ("name", models.CharField(max_length=120, verbose_name="название")),
                (
                    "slug",
                    models.SlugField(
                        max_length=120,
                        unique=True,
                        verbose_name="сегмент URL",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        db_index=True,
                        default=100,
                        verbose_name="порядок",
                    ),
                ),
                (
                    "is_published",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="опубликовано",
                    ),
                ),
            ],
            options={
                "verbose_name": "категория новостей",
                "verbose_name_plural": "категории новостей",
                "ordering": ("sort_order", "name"),
            },
        ),
        migrations.AddField(
            model_name="news",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="news",
                to="content.newscategory",
                verbose_name="категория",
            ),
        ),
        migrations.RunPython(_seed_and_assign, _clear_categories),
    ]
