"""Django Admin for SiteSettings singleton."""

from __future__ import annotations

from typing import Any

from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from sitesettings.credentials import token_source_label
from sitesettings.models import SiteSettings


class SiteSettingsAdminForm(forms.ModelForm):
    """Keep existing bot tokens when password fields are left blank."""

    class Meta:
        model = SiteSettings
        fields = "__all__"
        widgets = {
            "telegram_bot_token": forms.PasswordInput(
                render_value=False,
                attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
            ),
            "vk_access_token": forms.PasswordInput(
                render_value=False,
                attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
            ),
            "max_bot_token": forms.PasswordInput(
                render_value=False,
                attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
            ),
        }

    def clean_telegram_bot_token(self) -> str:
        """Blank input keeps the previously saved token."""
        return self._keep_secret_if_blank("telegram_bot_token")

    def clean_vk_access_token(self) -> str:
        """Blank input keeps the previously saved token."""
        return self._keep_secret_if_blank("vk_access_token")

    def clean_max_bot_token(self) -> str:
        """Blank input keeps the previously saved token."""
        return self._keep_secret_if_blank("max_bot_token")

    def _keep_secret_if_blank(self, field_name: str) -> str:
        """Return new value or existing instance value when form field is empty.

        Args:
            field_name: model field name for the secret.

        Returns:
            Token string to persist.
        """
        value = (self.cleaned_data.get(field_name) or "").strip()
        if value:
            return value
        if self.instance.pk:
            return getattr(self.instance, field_name) or ""
        return ""


@admin.register(SiteSettings)
class SiteSettingsAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Singleton Admin: edit only; no add/delete when row exists."""

    form = SiteSettingsAdminForm
    list_display = (
        "__str__",
        "show_prices_on_site",
        "yandex_metrika_id",
        "social_announce_on_publish",
        "updated_at",
    )
    list_display_links = ("__str__",)
    readonly_fields = (
        "telegram_token_status",
        "vk_token_status",
        "max_token_status",
        "created_at",
        "updated_at",
    )
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
                    "ID загружаются на сайте только после согласия в баннере "
                    "конфиденциальности. Можно также задать через файл окружения "
                    "или VITE_* как запасной вариант."
                ),
            },
        ),
        (
            "Интеграции: Telegram",
            {
                "fields": (
                    "telegram_enabled",
                    "telegram_bot_token",
                    "telegram_token_status",
                    "telegram_chat_id",
                ),
                "description": (
                    "Токен и ID канала/чата для бота. Пустой токен при сохранении "
                    "не затирает уже сохранённый. Запасной вариант — файл окружения."
                ),
            },
        ),
        (
            "Интеграции: VK",
            {
                "fields": (
                    "vk_enabled",
                    "vk_access_token",
                    "vk_token_status",
                    "vk_group_id",
                ),
                "description": (
                    "Ключ сообщества и ID группы (без минуса). Пустой токен при "
                    "сохранении не затирает уже сохранённый."
                ),
            },
        ),
        (
            "Интеграции: MAX",
            {
                "fields": (
                    "max_enabled",
                    "max_bot_token",
                    "max_token_status",
                    "max_chat_id",
                ),
                "description": ("Токен бота MAX и ID чата. Пустой токен при сохранении не затирает уже сохранённый."),
            },
        ),
        (
            "Анонсы контента",
            {
                "fields": ("social_announce_on_publish",),
                "description": (
                    "Автоотправка при первой публикации статьи/новости. Журнал отправок — в разделе «Соцсети»."
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

    @admin.display(description="Статус токена Telegram")
    def telegram_token_status(self, obj: SiteSettings) -> str:
        """Show whether Telegram token is configured (not the value)."""
        label = token_source_label(
            obj.telegram_bot_token,
            getattr(settings, "TELEGRAM_BOT_TOKEN", ""),
        )
        return format_html("<strong>{}</strong>", label)

    @admin.display(description="Статус токена VK")
    def vk_token_status(self, obj: SiteSettings) -> str:
        """Show whether VK token is configured (not the value)."""
        label = token_source_label(
            obj.vk_access_token,
            getattr(settings, "VK_ACCESS_TOKEN", ""),
        )
        return format_html("<strong>{}</strong>", label)

    @admin.display(description="Статус токена MAX")
    def max_token_status(self, obj: SiteSettings) -> str:
        """Show whether MAX token is configured (not the value)."""
        label = token_source_label(
            obj.max_bot_token,
            getattr(settings, "MAX_BOT_TOKEN", ""),
        )
        return format_html("<strong>{}</strong>", label)

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
