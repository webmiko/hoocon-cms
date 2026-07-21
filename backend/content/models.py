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

import uuid

from django.contrib.postgres.search import SearchVectorField
from django.db import models

from catalog.validators import sanitize_upload_filename, validate_image_upload


def article_cover_upload_to(instance: Article, filename: str) -> str:
    """Store under article_covers/<slug>/<uuid>_<safe_basename>.webp."""
    safe = sanitize_upload_filename(filename)
    slug = instance.slug or "pending"
    return f"article_covers/{slug}/{uuid.uuid4().hex}_{safe}"


def news_cover_upload_to(instance: News, filename: str) -> str:
    """Store under news_covers/<slug>/<uuid>_<safe_basename>.webp."""
    safe = sanitize_upload_filename(filename)
    slug = instance.slug or "pending"
    return f"news_covers/{slug}/{uuid.uuid4().hex}_{safe}"


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

    title: models.CharField = models.CharField("заголовок", max_length=300)
    slug: models.SlugField = models.SlugField(
        "сегмент URL",
        max_length=300,
        unique=True,
        db_index=True,
    )
    body: models.TextField = models.TextField("текст", blank=True, default="")
    is_published: models.BooleanField = models.BooleanField(
        "опубликовано",
        default=True,
        db_index=True,
        help_text="Видимость в публичном API.",
    )
    published_at: models.DateTimeField | None = models.DateTimeField(
        "дата публикации",
        null=True,
        blank=True,
        db_index=True,
        help_text="Дата публикации (для сортировки/SEO); null = черновик.",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

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

    SearchVector (title A + body B) — для глобального поиска по сайту.
    """

    # Postgres FTS vector (auto-maintained by DB trigger; see migration).
    search_vector = SearchVectorField(
        "поисковый вектор",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta(_ContentBase.Meta):
        verbose_name = "страница"
        verbose_name_plural = "страницы"


class Article(_ContentBase):
    """Expert article (E-E-A-T content, /statyi/<slug>).

    Гайды, экспертные материалы, подборы. `published_at` — обязательная
    семантически для опубликованных статей, но в модели опциональна
    (черновики без даты). SearchVector (title A + body B) поддерживается
    Postgres-триггером (см. миграцию 0002).
    """

    excerpt: models.TextField = models.TextField(
        "анонс",
        blank=True,
        default="",
        help_text="Краткий анонс для списка /statyi (без HTML).",
    )
    cover: models.ImageField = models.ImageField(
        "обложка",
        upload_to=article_cover_upload_to,
        blank=True,
        null=True,
        validators=[validate_image_upload],
        help_text="Обложка статьи (JPEG/PNG/WebP).",
    )
    # Postgres FTS vector (auto-maintained by DB trigger; see migration).
    # Spec: ПЛАН §6 Iter 3 — FTS на Article (SearchVector title + body).
    search_vector = SearchVectorField(
        "поисковый вектор",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta(_ContentBase.Meta):
        verbose_name = "статья"
        verbose_name_plural = "статьи"


class News(_ContentBase):
    """Company news item (/novosti/<slug>).

    Анонсы продуктов, события, обновления. SearchVector (title A + body B)
    поддерживается Postgres-триггером (см. миграцию 0002).
    """

    cover: models.ImageField = models.ImageField(
        "обложка",
        upload_to=news_cover_upload_to,
        blank=True,
        null=True,
        validators=[validate_image_upload],
        help_text="Обложка новости (JPEG/PNG/WebP).",
    )
    # Postgres FTS vector (auto-maintained by DB trigger; see migration).
    # Spec: ПЛАН §6 Iter 3 — FTS на News (SearchVector title + body).
    search_vector = SearchVectorField(
        "поисковый вектор",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta(_ContentBase.Meta):
        verbose_name = "новость"
        verbose_name_plural = "новости"
