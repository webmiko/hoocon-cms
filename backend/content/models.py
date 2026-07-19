"""Content models for Hoocon CMS: Page / Article / News (TDD).

Spec: ПЛАН §6 Iter 3 — content app: Page / Article / News со slug;
docs/readiness-backend-ux.md §2.2 (content | Page, Article, News | E-E-A-T);
docs/seo-url-migration.md (slug = canonical path, напр. /company, /statyi).

Каждая модель имеет свой уникальный slug (канонический path-сегмент URL):
- Page    → /<slug>           (напр. /o-kompanii, /kontakty)
- Article → /statyi/<slug>    (E-E-A-T: гайды, экспертный контент)
- News    → /novosti/<slug>   (анонсы, новости компании)

`is_published` по умолчанию True (контент публичен). `published_at` —
опциональная дата публикации (для сортировки и SEO; null = черновик).
"""

from __future__ import annotations

from django.db import models


class _ContentBase(models.Model):
    """Common fields for Page / Article / News (DRY).

    Abstract base: title, slug (unique within subclass), body (HTML from
    CMS), is_published, published_at, created_at, updated_at. Subclasses
    get their own slug uniqueness constraint via `unique=True` on the
    field (Django creates a per-table unique constraint for abstract
    field inheritance).

    Args (fields):
        title: человекочитаемое имя (H1 / og:title).
        slug: канонический path-сегмент URL (уникален в рамках модели).
        body: HTML-контент (CMS); экранируется на фронте, см.
            security-baseline §3.6 (no dangerouslySetInnerHTML на user HTML).
        is_published: видимость в публичном API (default True).
        published_at: опц. дата публикации (для сортировки/SEO; null = draft).
        created_at / updated_at: авто-таймстампы.
    """

    title: models.CharField = models.CharField(max_length=300)
    slug: models.SlugField = models.SlugField(max_length=300, unique=True, db_index=True)
    body: models.TextField = models.TextField(blank=True, default="")
    is_published: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Видимость в публичном API.",
    )
    published_at: models.DateTimeField | None = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Дата публикации (для сортировки/SEO); null = черновик.",
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-published_at", "-created_at")

    def __str__(self) -> str:
        """Return the title for Admin and logs."""
        return self.title


class Page(_ContentBase):
    """Static CMS page (e.g. /o-kompanii, /kontakty, /dostavka).

    Канонический путь = /<slug>. Используется для служебных страниц,
    не имеющих даты публикации (статичный контент сайта).
    """

    class Meta(_ContentBase.Meta):
        verbose_name = "страница"
        verbose_name_plural = "страницы"


class Article(_ContentBase):
    """Expert article (E-E-A-T content, /statyi/<slug>).

    Гайды, экспертные материалы, подборы. `published_at` — обязательная
    семантически для опубликованных статей, но в модели опциональна
    (черновики без даты). Slice 17 добавит SearchVector по title+body.
    """

    class Meta(_ContentBase.Meta):
        verbose_name = "статья"
        verbose_name_plural = "статьи"


class News(_ContentBase):
    """Company news item (/novosti/<slug>).

    Анонсы продуктов, события, обновления. Slice 17 добавит SearchVector.
    """

    class Meta(_ContentBase.Meta):
        verbose_name = "новость"
        verbose_name_plural = "новости"
