"""Telegram bot: welcome commands + free-text support inbox ingest."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from social.publishers import PublishResult, publish_telegram

logger = logging.getLogger("hoocon.social")

_COMMAND_RE = re.compile(
    r"^/(?P<cmd>[a-zA-Z0-9_]+)(?:@(?P<bot>[A-Za-z0-9_]+))?(?:\s|$)",
)
_TELEGRAM_CAPTION_MAX = 1024
_CHANNEL_URL = "https://t.me/hoocon_moscow"
_DEFAULT_WELCOME_STATIC = Path("static/social/telegram-welcome.webp")


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
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    text = (
        "<b>HOOCON</b> — электроприводы и арматура для вентиляции и ОВК.\n\n"
        f'Канал: <a href="{_CHANNEL_URL}">@hoocon_moscow</a>\n'
        f'Каталог: <a href="{site}">hoocon.ru</a>\n'
        f'Заявка / RFQ: <a href="{site}/consultation">на сайте</a>\n\n'
        "Команды: /channel · /site · /help\n"
        "Или просто напишите сообщение — ответит менеджер."
    )
    if len(text) > _TELEGRAM_CAPTION_MAX:
        return text[: _TELEGRAM_CAPTION_MAX - 1].rstrip() + "…"
    return text


def compose_channel_reply() -> str:
    """Plain HTML reply for /channel."""
    return f'Официальный канал: <a href="{_CHANNEL_URL}">Hoocon Москва</a>'


def compose_site_reply() -> str:
    """Plain HTML reply for /site."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    return f'Сайт и каталог: <a href="{site}">hoocon.ru</a>'


def compose_fallback_reply() -> str:
    """Reply when the message is not a known command."""
    return "Пока доступны команды: /start · /channel · /site · /help"


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
        return publish_telegram(chat_id=chat_id, text=auto.body)
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

    command = parse_bot_command(text)
    chat_key = str(chat_id)
    display_name = _display_name_from_message(message)

    if command in {"start", "help"}:
        caption = compose_welcome_caption()
        local = welcome_photo_path()
        result = publish_telegram(
            chat_id=chat_key,
            text=caption,
            photo_path=local,
            photo_url=None if local is not None else welcome_photo_url(),
        )
        if not result.ok and not result.skipped:
            logger.warning("telegram_welcome_photo_failed falling_back_to_text")
            return publish_telegram(chat_id=chat_key, text=caption)
        return result

    if command == "channel":
        return publish_telegram(chat_id=chat_key, text=compose_channel_reply())
    if command == "site":
        return publish_telegram(chat_id=chat_key, text=compose_site_reply())
    if command is not None:
        return publish_telegram(chat_id=chat_key, text=compose_fallback_reply())

    return _ingest_support_text(
        chat_id=chat_key,
        text=text,
        message=message,
        display_name=display_name,
    )
