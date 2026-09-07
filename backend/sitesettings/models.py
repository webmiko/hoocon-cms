"""SiteSettings singleton — глобальные настройки сайта.

Spec: ПЛАН §6 Iter 1; docs/security-baseline.md §3.2 (цены скрыты по умолчанию).
Паттерн singleton: ровно одна строка с pk=1. Доступ — через SiteSettings.load().
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
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

    Маршрутизация заявок (``lead_routing_mode``) и staff Web Push
    (``staff_push_*``) — только Admin; в публичный API не отдаются.
    """

    class LeadRoutingMode(models.TextChoices):
        OFF = "off", "Выкл — всё на общий ящик отдела продаж, без автоназначения"
        ASSIGN_SALES = (
            "assign_sales",
            "Назначать менеджеру, письмо на общий ящик отдела продаж",
        )
        ASSIGN_MANAGER = (
            "assign_manager",
            "Назначать менеджеру, письмо менеджеру",
        )

    SINGLETON_PK = 1

    show_prices_on_site: models.BooleanField = models.BooleanField(
        "показывать цены на сайте",
        default=False,
        help_text=("Показывать цены в публичном API и на сайте. По умолчанию выкл. — цены скрыты (политика RFQ)."),
    )

    # ── Lead routing (Admin only; not in public settings API) ──
    lead_routing_mode: models.CharField = models.CharField(
        "распределение заявок",
        max_length=32,
        choices=LeadRoutingMode.choices,
        default=LeadRoutingMode.OFF,
        help_text=(
            "Пул — только сотрудники группы «Менеджер» со статусом «Активен», "
            "статусом персонала и адресом в профиле (логин). Неактивные в очередь "
            "и письма не попадают. Выкл: письмо на LEAD_NOTIFY_EMAIL, без "
            "назначения. «Назначать…»: равномерная очередь; при одном менеджере "
            "всегда он. Пустой пул = как Выкл."
        ),
    )
    lead_rr_last_user: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="последний назначенный в очереди",
        help_text="Курсор очереди распределения (служебное; меняется автоматически).",
        limit_choices_to={"is_staff": True},
    )

    # ── Staff browser notifications (Admin only; not in public API) ──
    staff_push_leads_enabled: models.BooleanField = models.BooleanField(
        "уведомления на устройство при новой заявке",
        default=True,
        help_text=(
            "Браузерные уведомления в установленном приложении админки при новой "
            "заявке / консультации / замене. Сотрудник включает их у себя "
            "(список заявок или «Ещё»)."
        ),
    )
    staff_push_support_enabled: models.BooleanField = models.BooleanField(
        "уведомления на устройство при сообщении в поддержке",
        default=True,
        help_text=("Браузерные уведомления в админке при входящем сообщении в чате поддержки."),
    )
    staff_push_lead_title: models.CharField = models.CharField(
        "заголовок уведомления: заявка",
        max_length=80,
        blank=True,
        default="Новая заявка",
        help_text="Пусто = «Новая заявка».",
    )
    staff_push_lead_body: models.CharField = models.CharField(
        "текст уведомления: заявка",
        max_length=200,
        blank=True,
        default="{имя}: {тип}",
        help_text="Подстановки в фигурных скобках: имя, тип. Пусто = шаблон по умолчанию.",
    )
    staff_push_support_title: models.CharField = models.CharField(
        "заголовок уведомления: поддержка",
        max_length=80,
        blank=True,
        default="Новое сообщение в поддержке",
        help_text="Пусто = «Новое сообщение в поддержке».",
    )
    staff_push_support_body: models.CharField = models.CharField(
        "текст уведомления: поддержка",
        max_length=200,
        blank=True,
        default="{метка}: новое обращение",
        help_text=("Подстановка в фигурных скобках: метка (имя или канал). Пусто = шаблон по умолчанию."),
    )

    # ── Staff Telegram DMs (Admin only; personal chat_id on StaffTelegramProfile) ──
    staff_telegram_leads_enabled: models.BooleanField = models.BooleanField(
        "Telegram при новой заявке (если нет уведомлений на устройстве)",
        default=True,
        help_text=(
            "Личные сообщения бота, только если у сотрудника нет активных "
            "браузерных уведомлений админки. Почта по заявкам — всегда; "
            "уведомления на устройстве — доп. канал. Нужен ID чата (команда бота)."
        ),
    )
    staff_telegram_support_enabled: models.BooleanField = models.BooleanField(
        "Telegram при сообщении в поддержке (если нет уведомлений на устройстве)",
        default=True,
        help_text=("Входящий чат → Telegram только без браузерных уведомлений. Почта на первое обращение — отдельно."),
    )
    staff_telegram_superuser_crm_enabled: models.BooleanField = models.BooleanField(
        "Telegram супер-админу по CRM (если нет уведомлений на устройстве)",
        default=True,
        help_text=(
            "Статус/ответственный, ответ сотрудника в чате, заметки CRM — "
            "супер-админам без активных браузерных уведомлений."
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
