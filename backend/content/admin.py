"""Admin registration for content models: Page / Article / News."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from content.models import Article, News, NewsCategory, Page
from social.admin import SocialAnnounceAdminMixin, maybe_auto_announce


class _ContentBaseAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Shared admin config for Page / Article / News (DRY)."""

    list_display = ("title", "slug", "is_published", "published_at", "updated_at")
    list_display_links = ("title",)
    list_filter = ("is_published",)
    search_fields = ("title", "slug", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-published_at", "-created_at")


@admin.register(NewsCategory)
class NewsCategoryAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Rubrics for /novosti filter chips."""

    list_display = ("name", "slug", "sort_order", "is_published")
    list_display_links = ("name",)
    list_filter = ("is_published",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")


@admin.register(Page)
class PageAdmin(_ContentBaseAdmin):
    """Static CMS page admin (/o-kompanii, /kontakty, …)."""

    verbose_name = "Страница"


@admin.register(Article)
class ArticleAdmin(SocialAnnounceAdminMixin, _ContentBaseAdmin):
    """Expert article admin (/statyi/<slug>)."""

    change_form_template = "admin/content/change_form_social.html"
    verbose_name = "Статья"
    list_display = (
        "title",
        "slug",
        "is_published",
        "published_at",
        "updated_at",
    )
    search_fields = ("title", "slug", "body", "excerpt")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "title",
        "slug",
        "excerpt",
        "cover",
        "cover_dark",
        "body",
        "is_published",
        "published_at",
        "created_at",
        "updated_at",
    )

    def save_model(
        self,
        request: HttpRequest,
        obj: Article,
        form: Any,
        change: bool,
    ) -> None:
        """Persist article and optionally auto-announce on first publish."""
        was_published = False
        if change and obj.pk:
            was_published = Article.objects.filter(pk=obj.pk).values_list("is_published", flat=True).first() or False
        super().save_model(request, obj, form, change)
        maybe_auto_announce(obj, was_published=was_published)


@admin.register(News)
class NewsAdmin(SocialAnnounceAdminMixin, _ContentBaseAdmin):
    """Company news admin (/novosti/<slug>)."""

    change_form_template = "admin/content/change_form_social.html"
    verbose_name = "Новость"
    list_display = (
        "title",
        "slug",
        "category",
        "is_published",
        "published_at",
        "updated_at",
    )
    list_filter = ("is_published", "category")
    fields = (
        "title",
        "slug",
        "category",
        "cover",
        "body",
        "is_published",
        "published_at",
        "created_at",
        "updated_at",
    )

    def save_model(
        self,
        request: HttpRequest,
        obj: News,
        form: Any,
        change: bool,
    ) -> None:
        """Persist news and optionally auto-announce on first publish."""
        was_published = False
        if change and obj.pk:
            was_published = News.objects.filter(pk=obj.pk).values_list("is_published", flat=True).first() or False
        super().save_model(request, obj, form, change)
        maybe_auto_announce(obj, was_published=was_published)
