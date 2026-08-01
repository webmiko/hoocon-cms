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
    задаются в Admin (поле ниже) или запасным вариантом в ``.env``
    (TELEGRAM_BOT_TOKEN / VK_ACCESS_TOKEN / MAX_BOT_TOKEN). В публичный API
    токены и chat ID **не** попадают.
    """

    SINGLETON_PK = 1

    show_prices_on_site: models.BooleanField = models.BooleanField(
        "показывать цены на сайте",
        default=False,
        help_text=("Показывать цены в публичном API и на сайте. По умолчанию выкл. — цены скрыты (политика RFQ)."),
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
        "идентификатор Google Analytics 4",
        max_length=32,
        blank=True,
        default="",
        help_text="Идентификатор вида G-XXXXXXXX. Пусто = не подключать.",
    )

    # ── Social announce policy ──
    social_announce_on_publish: models.BooleanField = models.BooleanField(
        "автоанонс при публикации",
        default=False,
        help_text=("При первой публикации статьи/новости отправить анонс во все включённые каналы (фоновая очередь)."),
    )

    # ── Telegram integration ──
    telegram_enabled: models.BooleanField = models.BooleanField(
        "Telegram включён",
        default=False,
    )
    telegram_bot_token: models.CharField = models.CharField(
        "токен бота Telegram",
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Токен бота (@BotFather). Пустое поле при сохранении не стирает "
            "уже сохранённый токен. Запасной вариант: TELEGRAM_BOT_TOKEN "
            "в файле окружения."
        ),
    )
    telegram_chat_id: models.CharField = models.CharField(
        "ID чата / канала Telegram",
        max_length=64,
        blank=True,
        default="",
        help_text="ID канала или чата (напр. -100… или @имя_канала).",
    )

    # ── VK integration ──
    vk_enabled: models.BooleanField = models.BooleanField(
        "VK включён",
        default=False,
    )
    vk_access_token: models.CharField = models.CharField(
        "токен доступа VK",
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Ключ сообщества с правом публикации на стене. Пустое поле при "
            "сохранении не стирает токен. Запасной вариант: VK_ACCESS_TOKEN "
            "в файле окружения."
        ),
    )
    vk_group_id: models.CharField = models.CharField(
        "ID сообщества VK",
        max_length=32,
        blank=True,
        default="",
        help_text="Числовой ID сообщества (без минуса).",
    )

    # ── MAX integration ──
    max_enabled: models.BooleanField = models.BooleanField(
        "MAX включён",
        default=False,
    )
    max_bot_token: models.CharField = models.CharField(
        "токен бота MAX",
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Токен бота MAX. Пустое поле при сохранении не стирает токен. "
            "Запасной вариант: MAX_BOT_TOKEN в файле окружения."
        ),
    )
    max_chat_id: models.CharField = models.CharField(
        "ID чата MAX",
        max_length=64,
        blank=True,
        default="",
        help_text="ID чата для бота MAX.",
    )

    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "интеграция"
        verbose_name_plural = "интеграции"

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
        return "Интеграции сайта"
