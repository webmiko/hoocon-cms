"""Django Admin for SiteSettings singleton."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from sitesettings.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton Admin: edit only; no add/delete when row exists."""

    list_display = (
        "__str__",
        "show_prices_on_site",
        "yandex_metrika_id",
        "social_announce_on_publish",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Каталог",
            {"fields": ("show_prices_on_site",)},
        ),
        (
            "Счётчики аналитики",
            {
                "fields": ("yandex_metrika_id", "ga4_measurement_id"),
                "description": (
                    "ID загружаются на сайте только после согласия на cookies. "
                    "Можно также задать через .env / VITE_* как запасной вариант."
                ),
            },
        ),
        (
            "Анонсы в соцсети",
            {
                "fields": (
                    "social_announce_on_publish",
                    "telegram_enabled",
                    "telegram_chat_id",
                    "vk_enabled",
                    "vk_group_id",
                    "max_enabled",
                    "max_chat_id",
                ),
                "description": (
                    "Токены ботов хранятся только в .env: TELEGRAM_BOT_TOKEN, "
                    "VK_ACCESS_TOKEN, MAX_BOT_TOKEN. Здесь — флаги и ID чатов."
                ),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Allow add only if singleton row is missing."""
        if SiteSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(
        self,
        request: HttpRequest | None,
        obj: Any = None,
    ) -> bool:
        """Never allow delete — singleton must remain."""
        return False
