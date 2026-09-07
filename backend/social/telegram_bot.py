"""Telegram bot: welcome commands + reply keyboard + free-text support ingest."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from social.publishers import PublishResult, publish_telegram, telegram_api_call

logger = logging.getLogger("hoocon.social")

_COMMAND_RE = re.compile(
    r"^/(?P<cmd>[a-zA-Z0-9_]+)(?:@(?P<bot>[A-Za-z0-9_]+))?(?:\s|$)",
)
_TELEGRAM_CAPTION_MAX = 1024
_TELEGRAM_MESSAGE_MAX = 4096
_DEFAULT_CHANNEL_USERNAME = "hoocon_moscow"
_DEFAULT_WELCOME_STATIC = Path("static/social/telegram-welcome.webp")

# Site copy (aligned with seed_site_content / WhereToBuyPage).
_PHONE = "8 800 350-58-98"
_EMAIL_SALES = "sales@hoocon.ru"
_EMAIL_INFO = "info@hoocon.ru"
_HOURS = "Пн–Пт 9:30–17:30 (МСК), сб–вс — выходной"
_ADDRESS = "143440, Московская область, г. о. Красногорск, пгт Путилково, тер. Гринвуд, стр. 7, помещ. 98 (3-й этаж)"
_INN = "5024199634"
_KPP = "502401001"
_OGRN = "1195081070986"
_BANK = "р/с 40702810838000199148, к/с 30101810400000000225, БИК 044525225, ПАО Сбербанк"


def telegram_channel_username() -> str:
    """Public channel @username (no @) for menu replies and deep links."""
    raw = getattr(settings, "TELEGRAM_CHANNEL_USERNAME", "").strip().lstrip("@")
    return raw or _DEFAULT_CHANNEL_USERNAME


def telegram_channel_url() -> str:
    """HTTPS t.me URL for the official channel."""
    return f"https://t.me/{telegram_channel_username()}"


# Reply-keyboard labels → internal command names (exact button text only).
BTN_CHANNEL = "Перейти в канал"
BTN_SITE = "На сайт"
BTN_CONTACTS = "Контакты"
BTN_WHERE_TO_BUY = "Где купить"

_MENU_TEXT_ALIASES: dict[str, str] = {
    BTN_CHANNEL.lower(): "channel",
    BTN_SITE.lower(): "site",
    BTN_CONTACTS.lower(): "contacts",
    BTN_WHERE_TO_BUY.lower(): "where",
}

# Public BotFather menu only — /chatid stays hidden (staff who know it still get a reply).
BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Начать"},
    {"command": "channel", "description": "Перейти в канал"},
    {"command": "site", "description": "На сайт"},
    {"command": "contacts", "description": "Контакты и реквизиты"},
    {"command": "where", "description": "Где купить в розницу"},
]


def main_menu_keyboard() -> dict[str, Any]:
    """Persistent reply keyboard: канал · сайт · контакты · где купить."""
    return {
        "keyboard": [
            [{"text": BTN_CHANNEL}],
            [{"text": BTN_SITE}, {"text": BTN_CONTACTS}],
            [{"text": BTN_WHERE_TO_BUY}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Напишите ваш вопрос…",
    }


def welcome_photo_path() -> Path | None:
    """Local cover file shipped with the app (preferred for sendPhoto)."""
    configured = getattr(settings, "TELEGRAM_WELCOME_PHOTO_PATH", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    base = Path(settings.BASE_DIR)
    candidates.append(base / _DEFAULT_WELCOME_STATIC)
    for path in candidates:
        if path.is_file():
            return path
    return None


def welcome_photo_url() -> str:
    """Public HTTPS URL fallback when local cover file is missing."""
    configured = getattr(settings, "TELEGRAM_WELCOME_PHOTO_URL", "").strip()
    if configured:
        return configured
    return "https://hoocon.ru/og-image.jpg"


def _clip(text: str, limit: int) -> str:
    """Trim to Telegram length limits with an ellipsis when needed."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def compose_welcome_caption() -> str:
    """HTML caption for /start (Telegram HTML subset, ≤1024)."""
    text = (
        "<b>HOOCON</b> — электроприводы и арматура для вентиляции и ОВК.\n\n"
        "Кнопки меню:\n"
        f"• <b>{html.escape(BTN_CHANNEL)}</b> — официальный Telegram-канал\n"
        f"• <b>{html.escape(BTN_SITE)}</b> — каталог и заявки на сайте\n"
        f"• <b>{html.escape(BTN_CONTACTS)}</b> — телефон, почта, адрес, реквизиты\n"
        f"• <b>{html.escape(BTN_WHERE_TO_BUY)}</b> — розничные партнёры\n\n"
        "Или просто напишите вопрос — мы ответим в этом чате."
    )
    return _clip(text, _TELEGRAM_CAPTION_MAX)


def compose_contacts_caption() -> str:
    """HTML caption for «Контакты» — site /kontakty + реквизиты (≤1024)."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    text = (
        "<b>Контакты ООО «Хогон»</b> (бренд Hoocon)\n"
        "Ответим до 2 рабочих часов в рабочие дни.\n\n"
        f"<b>Телефон:</b> {html.escape(_PHONE)}\n"
        f"<b>Продажи:</b> {html.escape(_EMAIL_SALES)}\n"
        f"<b>Сотрудничество / ПДн:</b> {html.escape(_EMAIL_INFO)}\n"
        f"<b>Адрес:</b> {html.escape(_ADDRESS)}\n"
        f"<b>Режим:</b> {html.escape(_HOURS)}\n\n"
        "<b>Реквизиты</b>\n"
        f"ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}\n"
        f"{html.escape(_BANK)}\n\n"
        f"Полная страница: {html.escape(site)}/kontakty"
    )
    return _clip(text, _TELEGRAM_CAPTION_MAX)


def compose_where_to_buy_reply() -> str:
    """HTML text for «Где купить» — retail partners from /gde-kupit."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    text = (
        "<b>Где купить в розницу</b>\n"
        "Физическим лицам удобнее обратиться к партнёру "
        "в своём городе. "
        "Юрлица могут заказать напрямую у ООО «Хогон» "
        f"({html.escape(_PHONE)}, {html.escape(_EMAIL_SALES)}).\n\n"
        "<b>«ТД Панорамавент» — Москва</b>\n"
        "ул. Производственная, д. 11, стр. 6\n"
        "+7 (495) 380-06-76 · info@panoramavent.ru\n"
        "Пн–Пт 9:00–19:00\n\n"
        "<b>ООО «Аэро Групп» — Москва</b>\n"
        "ул. Электрозаводская, д. 24, офис 306\n"
        "+7 (495) 780-31-41 · office@aerostarmsk.ru\n"
        "aerogrupp.ru · Telegram @aerogrupp\n"
        "Пн–Пт 9:00–18:00\n\n"
        "<b>ООО «Смарт Альянс» — Санкт-Петербург</b>\n"
        "Офис: ул. Мельничная, д. 16, корп. 1, этаж 3\n"
        "Склад: ул. Мельничная, д. 11\n"
        "8 (800) 333-28-19 · hoocon.spb.ru\n"
        "Пн–Пт 10:00–17:00\n\n"
        "<b>ООО «РосАвтоматизация» — Минск</b>\n"
        "ул. Мележа, 1\n"
        "+375 29 697-11-02 · mail.sensorica.by@gmail.com\n"
        "hoocon.by\n\n"
        f"Подробнее на сайте: {html.escape(site)}/gde-kupit"
    )
    return _clip(text, _TELEGRAM_MESSAGE_MAX)


def compose_channel_reply() -> str:
    """Reply for «Канал» / /channel — opens via Telegram deep link in text."""
    username = telegram_channel_username()
    url = telegram_channel_url()
    return f"Официальный канал Hoocon: {html.escape(url)}\nНажмите ссылку или откройте @{html.escape(username)}."


def compose_site_reply() -> str:
    """Reply for «Сайт» / /site."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    safe = html.escape(site)
    return f"Сайт и каталог: {safe}\nЗаявка / RFQ: {safe}/consultation"


def compose_chatid_reply(chat_id: str) -> str:
    """Reply for /chatid — staff copies this into Admin user card."""
    safe = html.escape(str(chat_id).strip())
    return (
        f"Ваш ID чата Telegram: <code>{safe}</code>\n\n"
        "Скопируйте число в админку → Пользователи → "
        "Telegram сотрудника."
    )


def compose_fallback_reply() -> str:
    """Reply when the message is not a known command."""
    return (
        f"Доступны кнопки: {html.escape(BTN_CHANNEL)} · "
        f"{html.escape(BTN_SITE)} · {html.escape(BTN_CONTACTS)} · "
        f"{html.escape(BTN_WHERE_TO_BUY)}.\n"
        "Или напишите вопрос обычным текстом — мы ответим в этом чате."
    )


def parse_bot_command(text: str) -> str | None:
    """Extract command name from message text (without leading slash)."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    match = _COMMAND_RE.match(raw)
    if match is None:
        return None
    return match.group("cmd").lower()


def resolve_menu_action(text: str) -> str | None:
    """Map /commands and reply-keyboard labels to action names."""
    command = parse_bot_command(text)
    if command is not None:
        return command
    key = (text or "").strip().lower()
    return _MENU_TEXT_ALIASES.get(key)


def sync_bot_commands() -> PublishResult:
    """Register BotFather-style command menu (setMyCommands)."""
    return telegram_api_call("setMyCommands", {"commands": BOT_COMMANDS})


def message_plain_text(message: dict[str, Any]) -> str | None:
    """Prefer ``text``, fall back to photo/document ``caption``."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption
    return None


def _display_name_from_message(message: dict[str, Any]) -> str:
    """Best-effort display name from Telegram ``from`` user."""
    sender = message.get("from")
    if not isinstance(sender, dict):
        return ""
    parts = [
        str(sender.get("first_name") or "").strip(),
        str(sender.get("last_name") or "").strip(),
    ]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    username = str(sender.get("username") or "").strip()
    return f"@{username}" if username else ""


def _publish_photo_or_text(
    *,
    chat_id: str,
    caption: str,
    reply_markup: dict[str, Any],
) -> PublishResult:
    """sendPhoto with welcome cover; fall back to text if photo fails."""
    local = welcome_photo_path()
    result = publish_telegram(
        chat_id=chat_id,
        text=caption,
        photo_path=local,
        photo_url=None if local is not None else welcome_photo_url(),
        reply_markup=reply_markup,
    )
    if not result.ok and not result.skipped:
        logger.warning("telegram_photo_failed falling_back_to_text")
        return publish_telegram(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
        )
    return result


def _ingest_support_text(
    *,
    chat_id: str,
    text: str,
    message: dict[str, Any],
    display_name: str,
) -> PublishResult | None:
    """Store free-form text in support inbox; optional outside-hours auto-reply."""
    from supportchat.models import Channel
    from supportchat.services import (
        SupportChatError,
        add_inbound_message,
        get_or_create_messenger_conversation,
    )

    external_message_id = str(message.get("message_id") or "").strip()
    try:
        conversation = get_or_create_messenger_conversation(
            Channel.TELEGRAM,
            chat_id,
            display_name=display_name,
        )
        _inbound, auto = add_inbound_message(
            conversation,
            text,
            external_message_id=external_message_id,
            raw_payload={"telegram_message_id": message.get("message_id")},
            display_name=display_name,
        )
    except SupportChatError:
        logger.warning("telegram_support_ingest_rejected chat_id=%s", chat_id)
        return None

    if auto is not None:
        return publish_telegram(
            chat_id=chat_id,
            text=html.escape(auto.body),
            reply_markup=main_menu_keyboard(),
        )
    return None


def handle_telegram_update(update: dict[str, Any]) -> PublishResult | None:
    """Process one Bot API update; send a reply when applicable."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    if chat.get("type") != "private":
        return None
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    text = message_plain_text(message)
    if text is None:
        return None

    action = resolve_menu_action(text)
    chat_key = str(chat_id)
    display_name = _display_name_from_message(message)
    keyboard = main_menu_keyboard()

    if action in {"start", "help"}:
        # /help kept as welcome alias for older clients; not in the menu.
        return _publish_photo_or_text(
            chat_id=chat_key,
            caption=compose_welcome_caption(),
            reply_markup=keyboard,
        )

    if action in {"contacts", "contact"}:
        return _publish_photo_or_text(
            chat_id=chat_key,
            caption=compose_contacts_caption(),
            reply_markup=keyboard,
        )

    if action in {"where", "gdekupit", "where_to_buy"}:
        return publish_telegram(
            chat_id=chat_key,
            text=compose_where_to_buy_reply(),
            reply_markup=keyboard,
        )

    if action == "channel":
        return publish_telegram(
            chat_id=chat_key,
            text=compose_channel_reply(),
            reply_markup=keyboard,
        )
    if action == "site":
        return publish_telegram(
            chat_id=chat_key,
            text=compose_site_reply(),
            reply_markup=keyboard,
        )
    if action == "chatid":
        return publish_telegram(
            chat_id=chat_key,
            text=compose_chatid_reply(chat_key),
            reply_markup=keyboard,
        )
    if action is not None:
        # Unknown /command — hint, do not invent free-text ingest for slash cmds.
        return publish_telegram(
            chat_id=chat_key,
            text=compose_fallback_reply(),
            reply_markup=keyboard,
        )

    return _ingest_support_text(
        chat_id=chat_key,
        text=text,
        message=message,
        display_name=display_name,
    )
