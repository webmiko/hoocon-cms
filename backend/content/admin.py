"""Admin registration for content models: Page / Article / News.

Spec: ПЛАН §6 Iter 3 — content app; docs/readiness-backend-ux.md §2.2.
Staff manages CMS content via Django Admin; public API is read-only.
"""

from __future__ import annotations

from django.contrib import admin

from content.models import Article, News, Page


class _ContentBaseAdmin(admin.ModelAdmin):
    """Shared admin config for Page / Article / News (DRY)."""

    list_display = ("title", "slug", "is_published", "published_at", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "slug", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-published_at", "-created_at")


@admin.register(Page)
class PageAdmin(_ContentBaseAdmin):
    """Static CMS page admin (/o-kompanii, /kontakty, …)."""

    verbose_name = "Страница"


@admin.register(Article)
class ArticleAdmin(_ContentBaseAdmin):
    """Expert article admin (/statyi/<slug>)."""

    verbose_name = "Статья"


@admin.register(News)
class NewsAdmin(_ContentBaseAdmin):
    """Company news admin (/novosti/<slug>)."""

    verbose_name = "Новость"
