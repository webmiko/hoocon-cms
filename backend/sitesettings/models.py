"""SiteSettings singleton — глобальные настройки сайта.

Spec: ПЛАН §6 Iter 1; docs/security-baseline.md §3.2 (цены скрыты по умолчанию).
Паттерн singleton: ровно одна строка с pk=1. Доступ — через SiteSettings.load().
"""

from __future__ import annotations

from typing import Any

from django.db import models


class SiteSettings(models.Model):
    """Singleton site-wide settings.

    Единственная строка (pk=1) хранит флаги, влияющие на публичный API и UI.
    `show_prices_on_site` — security-critical: по умолчанию False (цены скрыты);
    сериализатор каталога отдаёт цену только если True.

    Analytics IDs — публичные счётчики (без секретов). Токены ботов соцсетей
    только в ``.env`` (TELEGRAM_BOT_TOKEN / VK_ACCESS_TOKEN / MAX_BOT_TOKEN).
    """

    SINGLETON_PK = 1

    show_prices_on_site: models.BooleanField = models.BooleanField(
        "показывать цены на сайте",
        default=False,
        help_text=(
            "Показывать цены в публичном API/UI. По умолчанию False — "
            "цены скрыты (политика RFQ). См. docs/security-baseline.md §3.2."
        ),
    )

    # ── Analytics (public counter IDs; loaded after cookie consent) ──
    yandex_metrika_id: models.CharField = models.CharField(
        "ID Яндекс.Метрики",
        max_length=32,
        blank=True,
        default="",
        help_text="Числовой ID счётчика (напр. 12345678). Пусто = не подключать.",
    )
    ga4_measurement_id: models.CharField = models.CharField(
        "ID Google Analytics 4",
        max_length=32,
        blank=True,
        default="",
        help_text="Measurement ID вида G-XXXXXXXX. Пусто = не подключать.",
    )

    # ── Social announcements ──
    social_announce_on_publish: models.BooleanField = models.BooleanField(
        "автоанонс при публикации",
        default=False,
        help_text=("При первой публикации статьи/новости отправить анонс во все включённые каналы (Celery)."),
    )
    telegram_enabled: models.BooleanField = models.BooleanField(
        "Telegram включён",
        default=False,
    )
    telegram_chat_id: models.CharField = models.CharField(
        "Telegram chat ID",
        max_length=64,
        blank=True,
        default="",
        help_text="ID канала/чата. Токен бота — TELEGRAM_BOT_TOKEN в .env.",
    )
    vk_enabled: models.BooleanField = models.BooleanField(
        "VK включён",
        default=False,
    )
    vk_group_id: models.CharField = models.CharField(
        "VK group ID",
        max_length=32,
        blank=True,
        default="",
        help_text="Числовой ID сообщества (без минуса). Токен — VK_ACCESS_TOKEN в .env.",
    )
    max_enabled: models.BooleanField = models.BooleanField(
        "MAX включён",
        default=False,
    )
    max_chat_id: models.CharField = models.CharField(
        "MAX chat ID",
        max_length=64,
        blank=True,
        default="",
        help_text="ID чата для бота MAX. Токен — MAX_BOT_TOKEN в .env.",
    )

    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "настройки сайта"
        verbose_name_plural = "настройки сайта"

    @classmethod
    def load(cls) -> SiteSettings:
        """Return the singleton row, creating it with defaults if missing."""
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Force pk=1 and switch to UPDATE if singleton already exists."""
        self.pk = self.SINGLETON_PK
        existing = type(self).objects.filter(pk=self.SINGLETON_PK).first()
        if existing is not None:
            self._state.adding = False
            self.created_at = existing.created_at
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Prevent deletion — singleton must always exist."""
        raise RuntimeError(
            "SiteSettings is a singleton and cannot be deleted.",
        )

    def __str__(self) -> str:
        """Return Russian label for Admin/logs."""
        state = "да" if self.show_prices_on_site else "нет"
        return f"Настройки сайта (цены: {state})"
