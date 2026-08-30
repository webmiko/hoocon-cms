"""Aggregated first-party pageview stats for Admin.

Essential / first-party only: no third-party cookies. Counts live in our DB
(daily rollups). Spec: cookie consent «обязательные» + Admin analytics.
"""

from __future__ import annotations

from django.db import models


class ObjectType(models.TextChoices):
    """Coarse page kind inferred from the public SPA path."""

    HOME = "home", "Главная"
    PAGE = "page", "Страница"
    SKU = "sku", "Артикул"
    CATALOG = "catalog", "Каталог"
    ARTICLE = "article", "Статья"
    NEWS = "news", "Новость"
    SEARCH = "search", "Поиск"
    LEAD = "lead", "Заявка"
    OTHER = "other", "Прочее"


class PageDailyStat(models.Model):
    """Views and unique visitors for one path on one calendar day."""

    day = models.DateField("день", db_index=True)
    path = models.CharField("путь", max_length=512, db_index=True)
    object_type = models.CharField(
        "тип",
        max_length=16,
        choices=ObjectType.choices,
        default=ObjectType.OTHER,
        db_index=True,
    )
    object_key = models.CharField(
        "ключ объекта",
        max_length=255,
        blank=True,
        default="",
        help_text="Код артикула, страницы, статьи и т.п.",
    )
    title = models.CharField("заголовок", max_length=255, blank=True, default="")
    views = models.PositiveIntegerField("просмотры", default=0)
    unique_visitors = models.PositiveIntegerField("уникальные", default=0)

    class Meta:
        verbose_name = "статистика страницы за день"
        verbose_name_plural = "статистика страниц по дням"
        ordering = ("-day", "-views")
        constraints = [
            models.UniqueConstraint(
                fields=("day", "path"),
                name="analytics_pagedailystat_day_path_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("day", "object_type", "-views"),
                name="analytics_page_day_type_views",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day} {self.path} ({self.views})"


class SiteDailyStat(models.Model):
    """Site-wide views and unique visitors for one calendar day."""

    day = models.DateField("день", unique=True, db_index=True)
    views = models.PositiveIntegerField("просмотры", default=0)
    unique_visitors = models.PositiveIntegerField("уникальные", default=0)

    class Meta:
        verbose_name = "статистика сайта за день"
        verbose_name_plural = "статистика сайта по дням"
        ordering = ("-day",)

    def __str__(self) -> str:
        return f"{self.day} ({self.views})"
