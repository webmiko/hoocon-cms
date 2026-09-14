"""Admin registration for content models: Page / Article / News / Wiki."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from content.models import Article, News, NewsCategory, Page, WikiDocument
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

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("category")

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


@admin.register(WikiDocument)
class WikiDocumentAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Staff Wiki: HTML dashboards and runbooks (Admin-only, no public API)."""

    change_list_template = "admin/content/wikidocument/change_list.html"
    list_display = (
        "title",
        "category",
        "is_active",
        "sort_order",
        "updated_at",
        "preview_link",
    )
    list_display_links = ("title",)
    list_filter = ("is_active", "category")
    search_fields = ("title", "slug", "category", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "preview_link")
    ordering = ("category", "sort_order", "title")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "slug",
                    "category",
                    "summary",
                    "sort_order",
                    "is_active",
                    "preview_link",
                ),
            },
        ),
        ("HTML", {"fields": ("body",)}),
        (
            "Служебное",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="просмотр")
    def preview_link(self, obj: WikiDocument) -> str:
        if not obj.pk:
            return "—"
        url = reverse("admin:content_wikidocument_read", args=[obj.slug])
        return format_html('<a href="{}" target="_blank" rel="noopener">Открыть</a>', url)

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict | None = None,
    ) -> HttpResponse:
        extra = dict(extra_context or {})
        extra["hoocon_wiki_browse_url"] = reverse("admin:content_wikidocument_browse")
        return super().changelist_view(request, extra_context=extra)

    def get_urls(self) -> list:
        custom = [
            path(
                "browse/",
                self.admin_site.admin_view(self.browse_view),
                name="content_wikidocument_browse",
            ),
            path(
                "read/<slug:slug>/",
                self.admin_site.admin_view(self.read_view),
                name="content_wikidocument_read",
            ),
        ]
        return custom + super().get_urls()

    def browse_view(self, request: HttpRequest) -> HttpResponse:
        """Wiki index grouped by category with links to read/edit."""
        if not request.user.has_perm("content.view_wikidocument"):
            raise PermissionDenied
        docs = WikiDocument.objects.filter(is_active=True).order_by(
            "category",
            "sort_order",
            "title",
        )
        grouped: dict[str, list[WikiDocument]] = defaultdict(list)
        for doc in docs:
            grouped[doc.category or "Общее"].append(doc)
        context = {
            **self.admin_site.each_context(request),
            "title": "Вики",
            "opts": self.model._meta,
            "grouped_docs": dict(sorted(grouped.items())),
            "changelist_url": reverse("admin:content_wikidocument_changelist"),
        }
        return render(request, "admin/content/wikidocument/browse.html", context)

    def read_view(self, request: HttpRequest, slug: str) -> HttpResponse:
        """Render stored HTML for staff (full document or admin-wrapped fragment)."""
        if not request.user.has_perm("content.view_wikidocument"):
            raise PermissionDenied
        doc = get_object_or_404(WikiDocument, slug=slug, is_active=True)
        if doc.is_full_html_document:
            return HttpResponse(doc.body, content_type="text/html; charset=utf-8")
        context = {
            **self.admin_site.each_context(request),
            "title": doc.title,
            "doc": doc,
            "opts": self.model._meta,
            "browse_url": reverse("admin:content_wikidocument_browse"),
            "change_url": reverse("admin:content_wikidocument_change", args=[doc.pk]),
        }
        return render(request, "admin/content/wikidocument/read.html", context)
