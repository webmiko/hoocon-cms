"""Django Admin for SiteSettings singleton."""

from __future__ import annotations

from typing import Any

from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from sitesettings.credentials import token_source_label
from sitesettings.integration_dashboard import build_integration_dashboard
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
    change_list_template = "admin/sitesettings/sitesettings/change_list.html"
    list_display = (
        "__str__",
        "show_prices_on_site",
        "yandex_metrika_id",
        "social_announce_on_publish",
        "updated_at",
    )
    list_display_links = ("__str__",)
    readonly_fields = (
        "lead_rr_last_user",
        "staff_push_subscribers",
        "staff_telegram_subscribers",
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
            "Заявки с сайта",
            {
                "fields": ("lead_routing_mode", "lead_rr_last_user"),
                "description": (
                    "Куда слать уведомление о новой заявке и назначать ли "
                    "ответственного менеджера. В очередь попадают только "
                    "сотрудники группы «Менеджер» со статусом «Активен» и "
                    "адресом в профиле. Письмо менеджеру — на этот адрес."
                ),
            },
        ),
        (
            "Уведомления на устройство",
            {
                "fields": (
                    "staff_push_leads_enabled",
                    "staff_push_support_enabled",
                    "staff_push_lead_title",
                    "staff_push_lead_body",
                    "staff_push_support_title",
                    "staff_push_support_body",
                    "staff_push_subscribers",
                ),
                "description": (
                    "Глобальные флаги и тексты браузерных уведомлений админки. "
                    "У каждого сотрудника их ещё нужно включить на устройстве "
                    "(список заявок / поддержки или «Ещё»). Топики подписок — "
                    "в разделе уведомлений."
                ),
            },
        ),
        (
            "Telegram персоналу",
            {
                "fields": (
                    "staff_telegram_leads_enabled",
                    "staff_telegram_support_enabled",
                    "staff_telegram_superuser_crm_enabled",
                    "staff_telegram_subscribers",
                ),
                "description": (
                    "Каналы: почта всегда (заявки / первое обращение в чат); "
                    "браузерные уведомления — дополнительно; Telegram — только "
                    "если у сотрудника нет активных уведомлений на устройстве. "
                    "ID чата — в карточке пользователя (команда бота). "
                    "Менеджерам: заявки и чат. Супер-админу: то же плюс CRM."
                ),
            },
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

    @admin.display(description="Подписки персонала")
    def staff_push_subscribers(self, obj: SiteSettings) -> str:
        """List staff Web Push endpoints with links to edit topics."""
        del obj  # singleton context only
        from webpush.models import PushSubscription

        try:
            list_url = reverse("admin:webpush_pushsubscription_changelist")
        except Exception:  # noqa: BLE001
            list_url = ""
        rows = (
            PushSubscription.objects.filter(user__isnull=False, user__is_staff=True)
            .select_related("user")
            .order_by("user__email", "-last_seen_at")[:40]
        )
        if not rows:
            empty = "Пока нет подписок сотрудников."
            if list_url:
                return format_html(
                    '<p>{}</p><p><a href="{}?user__is_staff__exact=1">Открыть подписки</a></p>',
                    empty,
                    list_url,
                )
            return empty
        items: list[tuple[str, str, str]] = []
        for sub in rows:
            user = sub.user
            assert user is not None
            name = (user.get_username() or user.email or f"#{user.pk}").strip()
            topics: list[str] = []
            if sub.topic_support:
                topics.append("оповещения")
            if sub.topic_marketing:
                topics.append("новости")
            topic_label = ", ".join(topics) if topics else "выкл"
            change_url = reverse("admin:webpush_pushsubscription_change", args=[sub.pk])
            items.append((change_url, name, topic_label))
        html_list = format_html_join(
            "",
            '<li><a href="{}">{}</a> — {}</li>',
            items,
        )
        footer = ""
        if list_url:
            footer = format_html(
                '<p style="margin-top:0.75rem;"><a href="{}?user__is_staff__exact=1">Все подписки персонала →</a></p>',
                list_url,
            )
        return format_html('<ul style="margin:0;padding-left:1.25rem;">{}</ul>{}', html_list, footer)

    @admin.display(description="Сотрудники с Telegram")
    def staff_telegram_subscribers(self, obj: SiteSettings) -> str:
        """List staff with a personal Telegram chat id."""
        del obj
        from accounts.models import StaffTelegramProfile

        rows = (
            StaffTelegramProfile.objects.exclude(telegram_chat_id="")
            .select_related("user")
            .order_by("user__email")[:40]
        )
        if not rows:
            return (
                "Пока никто не привязал ID чата. В личке бота отправьте команду "
                "для получения ID → Пользователи → Telegram сотрудника."
            )
        items: list[tuple[str, str, str]] = []
        for profile in rows:
            user = profile.user
            name = (user.get_username() or user.email or f"#{user.pk}").strip()
            change_url = reverse("admin:auth_user_change", args=[user.pk])
            flag = "вкл" if profile.telegram_alerts_enabled else "выкл"
            role = "супер" if user.is_superuser else "сотрудник"
            items.append(
                (change_url, name, f"{profile.telegram_chat_id} · {role} · {flag}"),
            )
        return format_html(
            '<ul style="margin:0;padding-left:1.25rem;">{}</ul>',
            format_html_join("", '<li><a href="{}">{}</a> — {}</li>', items),
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

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Show integration status dashboard instead of a one-row table."""
        SiteSettings.load()
        context = dict(extra_context or {})
        context["integration_dashboard"] = build_integration_dashboard()
        return super().changelist_view(request, extra_context=context)

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
