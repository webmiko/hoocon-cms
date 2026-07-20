"""Admin for social announcement log + content announce actions."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from social.models import SocialPost
from social.services import announce_content, schedule_announce_on_commit


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    """Read-mostly log of social deliveries."""

    list_display = (
        "id",
        "channel",
        "status",
        "content_type",
        "object_id",
        "external_id",
        "created_at",
        "sent_at",
    )
    list_filter = ("channel", "status", "created_at")
    search_fields = ("message_preview", "external_id", "error_message")
    readonly_fields = (
        "content_type",
        "object_id",
        "channel",
        "status",
        "message_preview",
        "external_id",
        "error_message",
        "created_at",
        "sent_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Posts are created by announce service only."""
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        """Allow view; fields are readonly."""
        return request.user.is_staff


class SocialAnnounceAdminMixin:
    """Admin mixin: action + change-form button to announce Article/News."""

    actions = ("announce_to_social",)

    @admin.action(description=_("Опубликовать в соцсети (Telegram / VK / MAX)"))
    def announce_to_social(
        self,
        request: HttpRequest,
        queryset: models.QuerySet,
    ) -> None:
        """Staff action: force-announce selected published items."""
        published = queryset.filter(is_published=True)
        count = 0
        for obj in published:
            posts = announce_content(obj, force=True)
            count += len(posts)
        skipped = queryset.count() - published.count()
        self.message_user(
            request,
            _("Создано отправок: %(sent)s. Пропущено черновиков: %(skip)s.") % {"sent": count, "skip": skipped},
            messages.SUCCESS if count else messages.WARNING,
        )

    def get_urls(self) -> list:
        """Add custom announce URL for the change form button."""
        urls = super().get_urls()  # type: ignore[misc]
        info = self.opts.app_label, self.opts.model_name  # type: ignore[attr-defined]
        custom = [
            path(
                "<path:object_id>/announce-social/",
                self.admin_site.admin_view(self.announce_social_view),  # type: ignore[attr-defined]
                name=f"{info[0]}_{info[1]}_announce_social",
            ),
        ]
        return custom + urls

    def announce_social_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponseRedirect:
        """POST/GET handler: announce one object and redirect back."""
        model = self.model  # type: ignore[attr-defined]
        obj = model.objects.filter(pk=object_id).first()
        opts = self.opts  # type: ignore[attr-defined]
        changelist = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
        if obj is None:
            self.message_user(request, _("Объект не найден."), messages.ERROR)
            return HttpResponseRedirect(changelist)
        change_url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_change",
            args=[obj.pk],
        )
        if not obj.is_published:
            self.message_user(
                request,
                _("Сначала опубликуйте материал (is_published)."),
                messages.WARNING,
            )
            return HttpResponseRedirect(change_url)
        posts = announce_content(obj, force=True)
        self.message_user(
            request,
            _("Отправлено в соцсети: %(n)s канал(ов).") % {"n": len(posts)},
            messages.SUCCESS if posts else messages.WARNING,
        )
        return HttpResponseRedirect(change_url)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        """Inject announce URL into change form context."""
        extra_context = extra_context or {}
        opts = self.opts  # type: ignore[attr-defined]
        extra_context["social_announce_url"] = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_announce_social",
            args=[object_id],
        )
        return super().change_view(  # type: ignore[misc]
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )


def maybe_auto_announce(obj: models.Model, *, was_published: bool) -> None:
    """Schedule announce when content becomes published and flag is on.

    Args:
        obj: Article or News after save.
        was_published: previous is_published value.
    """
    from sitesettings.models import SiteSettings

    if not getattr(obj, "is_published", False):
        return
    if was_published:
        return
    site = SiteSettings.load()
    if not site.social_announce_on_publish:
        return
    schedule_announce_on_commit(obj, force=False)
