"""Telegram bot: welcome commands + reply keyboard + free-text support ingest."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from social.copy import EMAIL_SALES, PHONE, clip_text, compose_contacts_html, site_url
from social.publishers import PublishResult, publish_telegram, telegram_api_call

logger = logging.getLogger("hoocon.social")

_COMMAND_RE = re.compile(
    r"^/(?P<cmd>[a-zA-Z0-9_]+)(?:@(?P<bot>[A-Za-z0-9_]+))?(?:\s|$)",
)
_TELEGRAM_CAPTION_MAX = 1024
_TELEGRAM_MESSAGE_MAX = 4096
_DEFAULT_CHANNEL_USERNAME = "hoocon_moscow"
_DEFAULT_WELCOME_STATIC = Path("static/social/telegram-welcome.webp")


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
    return "https://hoocon-telegram-api.npok9.workers.dev/welcome.jpg"


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
    return clip_text(text, _TELEGRAM_CAPTION_MAX)


def compose_contacts_caption() -> str:
    """HTML caption for «Контакты» — site /kontakty + реквизиты (≤1024)."""
    return compose_contacts_html(limit=_TELEGRAM_CAPTION_MAX)


def compose_where_to_buy_reply() -> str:
    """HTML text for «Где купить» — retail partners from /gde-kupit."""
    site = site_url()
    text = (
        "<b>Где купить в розницу</b>\n"
        "Физическим лицам удобнее обратиться к партнёру "
        "в своём городе. "
        "Юрлица могут заказать напрямую у ООО «Хогон» "
        f"({html.escape(PHONE)}, {html.escape(EMAIL_SALES)}).\n\n"
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
    return clip_text(text, _TELEGRAM_MESSAGE_MAX)


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
    # Prefer public URL on workers.dev — Telegram cannot fetch hoocon.ru, and
    # multipart upload from the VPS often times out through the egress proxy.
    result = publish_telegram(
        chat_id=chat_id,
        text=caption,
        photo_url=welcome_photo_url(),
        reply_markup=reply_markup,
    )
    if not result.ok and not result.skipped:
        local = welcome_photo_path()
        if local is not None:
            result = publish_telegram(
                chat_id=chat_id,
                text=caption,
                photo_path=local,
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


def _telegram_message_attachment(
    message: dict[str, Any],
) -> tuple[Any, str, str] | None:
    """Best-effort photo/document download → ``(file, name, mime)`` or None."""
    from django.core.files.base import ContentFile

    from social.publishers import telegram_download_file

    file_id = ""
    name = ""
    mime = ""
    document = message.get("document")
    photos = message.get("photo")
    if isinstance(document, dict):
        file_id = str(document.get("file_id") or "")
        name = str(document.get("file_name") or "")[:200]
        mime = str(document.get("mime_type") or "")[:100]
    elif isinstance(photos, list):
        sizes = [p for p in photos if isinstance(p, dict) and p.get("file_id")]
        if sizes:
            biggest = max(sizes, key=lambda p: int(p.get("file_size") or 0))
            file_id = str(biggest["file_id"])
            mime = "image/jpeg"
    if not file_id:
        return None
    downloaded = telegram_download_file(file_id)
    if downloaded is None:
        return None
    data, fallback_name = downloaded
    name = name or fallback_name
    return ContentFile(data, name=name), name, mime


def telegram_message_has_attachment(message: dict[str, Any]) -> bool:
    """True when the message carries a photo/document we can ingest."""
    if isinstance(message.get("document"), dict) and message["document"].get("file_id"):
        return True
    photos = message.get("photo")
    return isinstance(photos, list) and any(isinstance(p, dict) and p.get("file_id") for p in photos)


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

    attachment = _telegram_message_attachment(message)
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
            attachment=attachment[0] if attachment else None,
            attachment_name=attachment[1] if attachment else "",
            attachment_mime=attachment[2] if attachment else "",
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


def _handle_staff_reply_callback_query(query: dict[str, Any]) -> PublishResult | None:
    """Manager taps a staff alert button — reply / note / transfer picker."""
    from social.telegram_staff_reply import (
        compose_staff_note_prompt,
        compose_staff_reply_prompt,
        parse_staff_alert_callback,
        set_pending_staff_reply,
        staff_transfer_keyboard_markup,
        staff_user_for_telegram_chat_id,
    )
    from supportchat.models import Conversation
    from supportchat.services import (
        assign_conversation,
        notify_conversation_assigned,
        staff_public_name,
    )

    parsed = parse_staff_alert_callback(str(query.get("data") or ""))
    if parsed is None:
        return None
    action, conv_id, target_uid = parsed
    query_id = str(query.get("id") or "").strip()
    raw_from = query.get("from")
    from_user = raw_from if isinstance(raw_from, dict) else {}
    user_key = str(from_user.get("id") or "")
    staff_user = staff_user_for_telegram_chat_id(user_key)
    if staff_user is None:
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": "Недоступно"},
            )
        return None

    conv = Conversation.objects.filter(pk=conv_id).select_related("assignee").first()
    if conv is None:
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": f"Диалог #{conv_id} не найден"},
            )
        return None
    if conv.assignee_id is not None and conv.assignee_id != staff_user.pk:
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {
                    "callback_query_id": query_id,
                    "text": f"Диалог уже взял {staff_public_name(conv.assignee)}",
                },
            )
        return None

    if action == "assign_to":
        from django.contrib.auth import get_user_model

        target = get_user_model().objects.filter(pk=target_uid or 0, is_active=True, is_staff=True).first()
        if target is None:
            if query_id:
                telegram_api_call(
                    "answerCallbackQuery",
                    {"callback_query_id": query_id, "text": "Сотрудник не найден"},
                )
            return None
        assign_conversation(conv, target, actor=staff_user)
        notify_conversation_assigned(conv, target, staff_user)
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": f"Передан: {staff_public_name(target)}"},
            )
        message = query.get("message")
        mid = message.get("message_id") if isinstance(message, dict) else None
        if mid:
            telegram_api_call(
                "editMessageReplyMarkup",
                {"chat_id": user_key, "message_id": mid, "reply_markup": {"inline_keyboard": []}},
            )
        return None

    if action == "assign":
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": f"Диалог #{conv_id}"},
            )
        return publish_telegram(
            chat_id=user_key,
            text=html.escape(f"Кому передать диалог #{conv_id}?"),
            reply_markup=staff_transfer_keyboard_markup(conv_id, exclude_pk=staff_user.pk),
        )

    if action == "note":
        set_pending_staff_reply(user_key, conv_id, mode="note")
        if query_id:
            telegram_api_call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": f"Диалог #{conv_id}"},
            )
        return publish_telegram(
            chat_id=user_key,
            text=html.escape(compose_staff_note_prompt(conv_id)),
        )

    set_pending_staff_reply(user_key, conv_id)
    if query_id:
        telegram_api_call(
            "answerCallbackQuery",
            {"callback_query_id": query_id, "text": f"Диалог #{conv_id}"},
        )
    return publish_telegram(
        chat_id=user_key,
        text=html.escape(compose_staff_reply_prompt(conv_id)),
    )


def _handle_rating_callback_query(query: dict[str, Any]) -> PublishResult | None:
    """Client taps ⭐ on a rating request — verify the presser owns the dialog."""
    from supportchat.models import Channel, Conversation
    from supportchat.services import (
        SupportChatError,
        parse_support_rating_callback,
        rate_conversation,
    )

    data = str(query.get("data") or "")
    parsed = parse_support_rating_callback(data)
    if parsed is None:
        return _handle_staff_reply_callback_query(query)
    conv_id, score = parsed
    query_id = str(query.get("id") or "").strip()
    raw_from = query.get("from")
    from_user = raw_from if isinstance(raw_from, dict) else {}
    user_key = str(from_user.get("id") or "")
    conv = Conversation.objects.filter(pk=conv_id, channel=Channel.TELEGRAM).first()
    ok = conv is not None and conv.external_user_id == user_key
    if ok and conv is not None:
        try:
            rate_conversation(conv, score)
        except SupportChatError:
            ok = False
    if query_id:
        telegram_api_call(
            "answerCallbackQuery",
            {
                "callback_query_id": query_id,
                "text": "Спасибо за оценку!" if ok else "Не удалось сохранить оценку",
            },
        )
    return None


def _try_staff_telegram_reply(chat_key: str, text: str) -> PublishResult | None:
    """Handle manager reply (#ID text) or help; None → treat as client message."""
    from social.max_staff_reply import parse_staff_reply_text
    from social.telegram_staff_reply import (
        clear_pending_staff_reply,
        compose_staff_account_notice,
        compose_staff_note_prompt,
        compose_staff_reply_help,
        compose_staff_reply_prompt,
        get_pending_staff_reply,
        staff_user_for_telegram_chat_id,
        submit_staff_reply_from_telegram,
    )

    def _send(body: str) -> PublishResult:
        return publish_telegram(chat_id=chat_key, text=html.escape(body))

    staff_user = staff_user_for_telegram_chat_id(chat_key)
    if staff_user is None:
        return None

    parsed = parse_staff_reply_text(text)
    if parsed is not None:
        clear_pending_staff_reply(chat_key)
    elif resolve_menu_action(text) is None:
        pending = get_pending_staff_reply(chat_key)
        body = (text or "").strip()
        raw = body.casefold()
        if pending is not None and body and not raw.startswith("/reply"):
            conv_id, mode = pending
            parsed = (conv_id, f"/note {body}" if mode == "note" else body)
            clear_pending_staff_reply(chat_key)

    if parsed is not None:
        conv_id, reply_body = parsed
        ok, status = submit_staff_reply_from_telegram(staff_user, conv_id, reply_body)
        return _send(status if ok else f"Не отправлено: {status}")

    raw = (text or "").strip().casefold()
    if raw.startswith("/reply"):
        return _send(compose_staff_reply_help())

    if resolve_menu_action(text) is not None:
        clear_pending_staff_reply(chat_key)
        return None

    pending = get_pending_staff_reply(chat_key)
    if pending is not None:
        pending_conv, pending_mode = pending
        if pending_mode == "note":
            return _send(compose_staff_note_prompt(pending_conv))
        return _send(compose_staff_reply_prompt(pending_conv))

    return _send(compose_staff_account_notice())


def handle_telegram_update(update: dict[str, Any]) -> PublishResult | None:
    """Process one Bot API update; send a reply when applicable."""
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        return _handle_rating_callback_query(callback_query)
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
        if not telegram_message_has_attachment(message):
            return None
        text = ""

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

    staff_handled = _try_staff_telegram_reply(chat_key, text)
    if staff_handled is not None:
        return staff_handled

    return _ingest_support_text(
        chat_id=chat_key,
        text=text,
        message=message,
        display_name=display_name,
    )
