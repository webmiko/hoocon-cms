"""Build Admin dashboard cards for SiteSettings integrations."""

from __future__ import annotations

from typing import Any, Literal

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from sitesettings.credentials import (
    max_bot_token,
    telegram_bot_token,
    token_source_label,
    vk_access_token,
)
from sitesettings.models import SiteSettings

Status = Literal["on", "partial", "off"]


def _status(enabled: bool, ready: bool) -> tuple[Status, str]:
    """Map enable flag + credentials readiness to UI status."""
    if enabled and ready:
        return "on", "Подключён"
    if enabled and not ready:
        return "partial", "Не полностью"
    if ready and not enabled:
        return "partial", "Готов, выключен"
    return "off", "Выключен"


def build_integration_dashboard(site: SiteSettings | None = None) -> dict[str, Any]:
    """Return context for the SiteSettings changelist dashboard.

    Args:
        site: Optional singleton; loaded when omitted.

    Returns:
        Dict with ``cards``, ``change_url``, ``social_log_url``, ``updated_at``.
    """
    row = site if site is not None else SiteSettings.load()
    change_url = reverse("admin:sitesettings_sitesettings_change", args=[row.pk])
    social_log_url = ""
    try:
        social_log_url = reverse("admin:social_socialpost_changelist")
    except NoReverseMatch:
        social_log_url = ""

    tg_token = telegram_bot_token(row)
    tg_ready = bool(tg_token and row.telegram_chat_id.strip())
    tg_status, tg_label = _status(row.telegram_enabled, tg_ready)

    vk_token = vk_access_token(row)
    vk_ready = bool(vk_token and row.vk_group_id.strip())
    vk_status, vk_label = _status(row.vk_enabled, vk_ready)

    max_token = max_bot_token(row)
    max_ready = bool(max_token and row.max_chat_id.strip())
    max_status, max_label = _status(row.max_enabled, max_ready)

    metrika = row.yandex_metrika_id.strip()
    ga4 = row.ga4_measurement_id.strip()

    cards: list[dict[str, Any]] = [
        {
            "name": "Telegram",
            "status": tg_status,
            "status_label": tg_label,
            "detail": (
                f"Канал: {row.telegram_chat_id.strip() or '—'}; "
                f"токен: "
                f"{token_source_label(row.telegram_bot_token, getattr(settings, 'TELEGRAM_BOT_TOKEN', ''))}"
            ),
            "hint": "Анонсы статей и новостей в канал",
        },
        {
            "name": "VK",
            "status": vk_status,
            "status_label": vk_label,
            "detail": (
                f"Группа: {row.vk_group_id.strip() or '—'}; "
                f"токен: "
                f"{token_source_label(row.vk_access_token, getattr(settings, 'VK_ACCESS_TOKEN', ''))}"
            ),
            "hint": "Публикации на стену сообщества",
        },
        {
            "name": "MAX",
            "status": max_status,
            "status_label": max_label,
            "detail": (
                f"Чат: {row.max_chat_id.strip() or '—'}; "
                f"токен: "
                f"{token_source_label(row.max_bot_token, getattr(settings, 'MAX_BOT_TOKEN', ''))}"
            ),
            "hint": "Сообщения бота MAX",
        },
        {
            "name": "Яндекс.Метрика",
            "status": "on" if metrika else "off",
            "status_label": "Задан" if metrika else "Не задан",
            "detail": metrika or "Счётчик не подключён",
            "hint": "Загрузка после согласия в баннере",
        },
        {
            "name": "Google Analytics 4",
            "status": "on" if ga4 else "off",
            "status_label": "Задан" if ga4 else "Не задан",
            "detail": ga4 or "Measurement ID не задан",
            "hint": "Загрузка после согласия в баннере",
        },
        {
            "name": "Цены на сайте",
            "status": "on" if row.show_prices_on_site else "off",
            "status_label": "Показываются" if row.show_prices_on_site else "Скрыты (RFQ)",
            "detail": "Публичный каталог",
            "hint": "По умолчанию цены скрыты",
        },
        {
            "name": "Автоанонс",
            "status": "on" if row.social_announce_on_publish else "off",
            "status_label": "Включён" if row.social_announce_on_publish else "Выключен",
            "detail": "При первой публикации статьи/новости",
            "hint": "Нужен рабочий Celery worker",
        },
    ]

    return {
        "cards": cards,
        "change_url": change_url,
        "social_log_url": social_log_url,
        "updated_at": row.updated_at,
        "connected_count": sum(1 for card in cards if card["status"] == "on"),
        "total_count": len(cards),
    }
