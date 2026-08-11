"""Telegram bot: welcome commands + reply keyboard + free-text support ingest."""

from __future__ import annotations

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
_CHANNEL_URL = "https://t.me/hoocon_moscow"
_DEFAULT_WELCOME_STATIC = Path("static/social/telegram-welcome.webp")

# Reply-keyboard labels → internal command names (interaction buttons).
BTN_CHANNEL = "Перейти в канал"
BTN_SITE = "На сайт"
BTN_HELP = "Помощь"

_MENU_TEXT_ALIASES: dict[str, str] = {
    BTN_CHANNEL.lower(): "channel",
    BTN_SITE.lower(): "site",
    BTN_HELP.lower(): "help",
    "канал": "channel",
    "сайт": "site",
}

BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Начать"},
    {"command": "channel", "description": "Перейти в канал"},
    {"command": "site", "description": "На сайт"},
    {"command": "help", "description": "Помощь"},
]


def main_menu_keyboard() -> dict[str, Any]:
    """Persistent reply keyboard: Перейти в канал · На сайт · Помощь."""
    return {
        "keyboard": [
            [{"text": BTN_CHANNEL}],
            [{"text": BTN_SITE}, {"text": BTN_HELP}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Напишите вопрос менеджеру…",
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


def compose_welcome_caption() -> str:
    """HTML caption for /start and /help (Telegram HTML subset, ≤1024)."""
    text = (
        "<b>HOOCON</b> — электроприводы и арматура для вентиляции и ОВК.\n\n"
        "Кнопки меню:\n"
        f"• <b>{BTN_CHANNEL}</b> — официальный Telegram-канал\n"
        f"• <b>{BTN_SITE}</b> — каталог и заявки на сайте\n"
        f"• <b>{BTN_HELP}</b> — эта подсказка\n\n"
        "Или просто напишите сообщение — ответит менеджер."
    )
    if len(text) > _TELEGRAM_CAPTION_MAX:
        return text[: _TELEGRAM_CAPTION_MAX - 1].rstrip() + "…"
    return text


def compose_channel_reply() -> str:
    """Reply for «Канал» / /channel — opens via Telegram deep link in text."""
    return f"Официальный канал Hoocon: {_CHANNEL_URL}\nНажмите ссылку или откройте @hoocon_moscow."


def compose_site_reply() -> str:
    """Reply for «Сайт» / /site."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    return f"Сайт и каталог: {site}\nЗаявка / RFQ: {site}/consultation"


def compose_fallback_reply() -> str:
    """Reply when the message is not a known command."""
    return f"Доступны кнопки: {BTN_CHANNEL} · {BTN_SITE} · {BTN_HELP}.\nИли напишите вопрос менеджеру обычным текстом."


def parse_bot_command(text: str) -> str | None:
    """Extract command name from message text (without leading slash).

    Args:
        text: Raw ``message.text`` (may include ``@BotName`` suffix).

    Returns:
        Lowercased command or None.
    """
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
            text=auto.body,
            reply_markup=main_menu_keyboard(),
        )
    return None


def handle_telegram_update(update: dict[str, Any]) -> PublishResult | None:
    """Process one Bot API update; send a reply when applicable.

    Args:
        update: Parsed Telegram Update object.

    Returns:
        PublishResult when a reply was attempted; None when ignored.
    """
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    action = resolve_menu_action(text)
    chat_key = str(chat_id)
    display_name = _display_name_from_message(message)
    keyboard = main_menu_keyboard()

    if action in {"start", "help"}:
        caption = compose_welcome_caption()
        local = welcome_photo_path()
        result = publish_telegram(
            chat_id=chat_key,
            text=caption,
            photo_path=local,
            photo_url=None if local is not None else welcome_photo_url(),
            reply_markup=keyboard,
        )
        if not result.ok and not result.skipped:
            logger.warning("telegram_welcome_photo_failed falling_back_to_text")
            return publish_telegram(
                chat_id=chat_key,
                text=caption,
                reply_markup=keyboard,
            )
        return result

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
    if action is not None:
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
