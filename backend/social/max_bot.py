"""MAX bot: welcome inline menu + free-text support ingest."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from social.publishers import PublishResult, publish_max
from social.telegram_bot import (
    _ADDRESS,
    _BANK,
    _EMAIL_INFO,
    _EMAIL_SALES,
    _HOURS,
    _INN,
    _KPP,
    _OGRN,
    _PHONE,
)

logger = logging.getLogger("hoocon.social")

_COMMAND_RE = re.compile(
    r"^/(?P<cmd>[a-zA-Z0-9_]+)(?:\s|$)",
)
_START_RE = re.compile(
    r"^/start(?:\s+(?P<payload>[a-zA-Z0-9_-]+))?\s*$",
    re.IGNORECASE,
)
_MESSAGE_MAX = 4000

# Deep-link codes for clients (?start=CODE). Printed by `manage.py max_setup_channel --codes`.
USER_START_CODES: dict[str, str] = {
    "support": "Поддержка и меню (виджет на сайте)",
    "catalog": "Каталог на сайте",
    "consultation": "Заявка / коммерческое предложение",
    "where": "Где купить в розницу",
    "contacts": "Контакты и реквизиты",
    "channel": "Ссылка на канал MAX",
}

# Slash commands in 1:1 bot chat (public menu + hidden staff).
BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Меню и поддержка"},
    {"command": "catalog", "description": "Каталог"},
    {"command": "consultation", "description": "Заявка / КП"},
    {"command": "where", "description": "Где купить"},
    {"command": "contacts", "description": "Контакты"},
    {"command": "channel", "description": "Канал MAX"},
    {"command": "help", "description": "Подсказка по командам"},
]

STAFF_COMMANDS: list[dict[str, str]] = [
    {"command": "chatid", "description": "Ваш user_id для алертов в Admin"},
    {"command": "reply", "description": "Ответ клиенту: /reply ID текст"},
]

BTN_CATALOG = "Каталог"
BTN_CONSULTATION = "Заявка / КП"
BTN_WHERE = "Где купить"
BTN_CONTACTS = "Контакты"
BTN_DOCS = "Документация"
BTN_FAQ = "FAQ"
BTN_PRIVACY = "Политика ПДн"
BTN_TERMS = "Соглашение"
BTN_OFFER = "Оферта"
BTN_CHANNEL = "Канал MAX"
BTN_COMPANY = "О компании"


def max_bot_username() -> str:
    """Public bot nick (no @) for deep links."""
    raw = getattr(settings, "MAX_BOT_USERNAME", "id5024199634_bot").strip().lstrip("@")
    return raw or "id5024199634_bot"


def max_channel_username() -> str:
    """Public channel nick (no @) for menu link."""
    raw = getattr(settings, "MAX_CHANNEL_USERNAME", "id5024199634_biz").strip().lstrip("@")
    return raw or "id5024199634_biz"


def max_bot_deep_link(start: str = "support") -> str:
    """HTTPS deep link to open 1:1 bot chat."""
    bot = max_bot_username()
    payload = (start or "support").strip()
    if payload:
        return f"https://max.ru/{bot}?start={payload}"
    return f"https://max.ru/{bot}"


def max_channel_deep_link() -> str:
    """HTTPS link to the official MAX channel."""
    return f"https://max.ru/{max_channel_username()}"


def _site_url() -> str:
    return getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")


def _page(path: str) -> str:
    base = _site_url()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _link_button(text: str, url: str) -> dict[str, str]:
    return {"type": "link", "text": text, "url": url}


def main_menu_keyboard() -> list[dict[str, Any]]:
    """Inline keyboard rows for MAX Bot API attachments."""
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        _link_button(BTN_CATALOG, _page("/catalog")),
                        _link_button(BTN_CONSULTATION, _page("/consultation")),
                        _link_button(BTN_WHERE, _page("/gde-kupit")),
                    ],
                    [
                        _link_button(BTN_CONTACTS, _page("/kontakty")),
                        _link_button(BTN_DOCS, _page("/dokumentaciya")),
                        _link_button(BTN_FAQ, _page("/faq")),
                    ],
                    [
                        _link_button(BTN_PRIVACY, _page("/privacy-policy")),
                        _link_button(BTN_TERMS, _page("/terms")),
                        _link_button(BTN_OFFER, _page("/oferta")),
                    ],
                    [
                        _link_button(BTN_CHANNEL, max_channel_deep_link()),
                        _link_button(BTN_COMPANY, _page("/company")),
                    ],
                ],
            },
        },
    ]


def compose_welcome_text() -> str:
    """Plain welcome for /start and bot_started."""
    text = (
        "Добро пожаловать в Hoocon!\n\n"
        "HOOCON — электроприводы и арматура для вентиляции и ОВК.\n\n"
        "Кнопки ниже — каталог, заявка, документы, контакты и канал MAX.\n"
        "Или напишите вопрос — ответим в рабочие дни.\n\n"
        f"Канал новостей: {max_channel_deep_link()}\n"
        f"Режим ответа: {_HOURS} · {_PHONE}"
    )
    return _clip(text, _MESSAGE_MAX)


def welcome_cover_path() -> Path | None:
    """Welcome cover reused from Telegram/MAX channel asset."""
    from social.max_channel import channel_cover_path

    return channel_cover_path()


def _welcome_attachments(token: str | None) -> list[dict[str, Any]]:
    """Cover image + inline menu for the first /start reply."""
    attachments: list[dict[str, Any]] = list(main_menu_keyboard())
    if not token:
        return attachments
    cover = welcome_cover_path()
    if cover is None:
        return attachments
    try:
        from social.max_http import max_upload_image

        image_token = max_upload_image(token, cover)
    except (OSError, RuntimeError, FileNotFoundError) as exc:
        logger.warning("max_welcome_cover_failed error=%s", type(exc).__name__)
        return attachments
    attachments.insert(0, {"type": "image", "payload": {"token": image_token}})
    return attachments


def compose_contacts_text() -> str:
    """Contacts + requisites (plain text)."""
    site = _site_url()
    text = (
        "Контакты ООО «Хогон» (бренд Hoocon)\n"
        "Ответим до 2 рабочих часов в рабочие дни.\n\n"
        f"Телефон: {_PHONE}\n"
        f"Продажи: {_EMAIL_SALES}\n"
        f"Сотрудничество / ПДн: {_EMAIL_INFO}\n"
        f"Адрес: {_ADDRESS}\n"
        f"Режим: {_HOURS}\n\n"
        f"ИНН {_INN}, КПП {_KPP}, ОГРН {_OGRN}\n"
        f"{_BANK}\n\n"
        f"Полная страница: {site}/kontakty"
    )
    return _clip(text, _MESSAGE_MAX)


def compose_chatid_reply(user_id: str) -> str:
    """Reply for /chatid — staff copies id into Admin user card."""
    safe = str(user_id).strip()
    return f"Ваш user_id в MAX: {safe}\n\nСкопируйте число в админку → Пользователи → MAX сотрудника."


def compose_fallback_reply() -> str:
    return (
        "Используйте кнопки меню или напишите вопрос текстом.\n"
        "Команды: /start, /catalog, /consultation, /where, /contacts, /channel.\n"
        "Сотрудникам: /chatid — ваш user_id для алертов."
    )


def compose_catalog_reply() -> str:
    return _clip(
        f"Каталог Hoocon: {_page('/catalog')}\n\n"
        "Электроприводы DA/SA/HV, клапаны, комплектующие. "
        "Подбор по серии и аналогам Belimo — на сайте или вопросом боту.",
        _MESSAGE_MAX,
    )


def compose_consultation_reply() -> str:
    return _clip(
        f"Заявка и коммерческое предложение: {_page('/consultation')}\n\n"
        "Опишите задачу текстом — менеджер ответит в рабочие дни.",
        _MESSAGE_MAX,
    )


def compose_where_reply() -> str:
    return _clip(
        f"Где купить Hoocon в розницу: {_page('/gde-kupit')}\n\n"
        "Дилеры и партнёры по регионам — на карте и в списке на сайте.",
        _MESSAGE_MAX,
    )


def compose_channel_reply() -> str:
    return _clip(
        f"Официальный канал Hoocon: {max_channel_deep_link()}\n\nНовости, анонсы каталога и статьи по подбору.",
        _MESSAGE_MAX,
    )


def parse_start_payload(text: str) -> str | None:
    """Return start deep-link code from `/start` or `/start code`, else None."""
    raw = (text or "").strip()
    match = _START_RE.match(raw)
    if not match:
        return None
    payload = (match.group("payload") or "support").strip().casefold()
    return payload or "support"


def resolve_start_action(payload: str) -> str:
    """Map ?start= payload to internal action name."""
    code = (payload or "support").strip().casefold()
    aliases = {
        "menu": "start",
        "help": "start",
        "support": "start",
        "kp": "consultation",
        "gdekupit": "where",
        "buy": "where",
        "contact": "contacts",
    }
    return aliases.get(code, code)


def interaction_codes_markdown() -> str:
    """Human-readable table of MAX deep links and staff commands."""
    bot = max_bot_username()
    lines = [
        "# MAX: коды взаимодействия Hoocon",
        "",
        "## Клиенты (deep link `?start=`)",
        "",
        "| Код | Назначение | Ссылка |",
        "|-----|------------|--------|",
    ]
    for code, label in USER_START_CODES.items():
        lines.append(f"| `{code}` | {label} | {max_bot_deep_link(code)} |")
    lines.extend(
        [
            "",
            "## Команды в чате с ботом",
            "",
            "| Команда | Кто | Назначение |",
            "|---------|-----|------------|",
        ],
    )
    for row in BOT_COMMANDS:
        lines.append(f"| `/{row['command']}` | клиент | {row['description']} |")
    for row in STAFF_COMMANDS:
        lines.append(f"| `/{row['command']}` | сотрудник | {row['description']} |")
    lines.extend(
        [
            "",
            "## Канал",
            "",
            f"- Ник: @{max_channel_username()}",
            f"- Ссылка: {max_channel_deep_link()}",
            f"- Бот: @{bot}",
            "",
            "После `/chatid` скопируйте user_id в Admin → Пользователи → MAX сотрудника.",
        ],
    )
    return "\n".join(lines)


def resolve_menu_action(text: str) -> str | None:
    """Map slash command or exact button label to internal action name."""
    raw = (text or "").strip()
    if not raw:
        return None
    start_payload = parse_start_payload(raw)
    if start_payload is not None:
        return resolve_start_action(start_payload)
    lower = raw.casefold()
    if lower in {BTN_CONTACTS.casefold()}:
        return "contacts"
    m = _COMMAND_RE.match(raw)
    if m:
        return m.group("cmd").casefold()
    return None


def _display_name_from_user(user: dict[str, Any]) -> str:
    first = (user.get("first_name") or user.get("name") or "").strip()
    last = (user.get("last_name") or "").strip()
    if first and last:
        return f"{first} {last}"[:200]
    return (first or last or "Клиент MAX")[:200]


def _message_plain_text(message: dict[str, Any]) -> str | None:
    body = message.get("body")
    if not isinstance(body, dict):
        return None
    text = (body.get("text") or "").strip()
    return text or None


def _message_external_id(message: dict[str, Any]) -> str:
    body = message.get("body")
    if isinstance(body, dict):
        mid = (body.get("mid") or "").strip()
        if mid:
            return mid
    return str(message.get("timestamp") or "")


def _send_to_user(
    user_id: str,
    text: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> PublishResult:
    return publish_max(
        user_id=user_id,
        text=text,
        attachments=attachments,
    )


def _send_welcome_to_user(user_id: str, text: str) -> PublishResult:
    """Welcome reply with cover image when the asset is available."""
    from sitesettings.credentials import max_bot_token

    token = max_bot_token()
    return _send_to_user(
        user_id,
        text,
        attachments=_welcome_attachments(token or None),
    )


def _send_reply_for_action(user_key: str, action: str) -> PublishResult:
    """Route menu action to welcome (with cover) or plain text reply."""
    reply_text, keyboard = _reply_for_action(action, user_key)
    if action in {"start", "help"}:
        return _send_welcome_to_user(user_key, reply_text)
    return _send_to_user(user_key, reply_text, attachments=keyboard)


def _try_staff_max_reply(user_key: str, text: str) -> PublishResult | None:
    """Handle manager reply (#ID text) or help; None → treat as client message."""
    from social.max_staff_reply import (
        compose_staff_reply_help,
        parse_staff_reply_text,
        staff_user_for_max_user_id,
        submit_staff_reply_from_max,
    )

    staff_user = staff_user_for_max_user_id(user_key)
    if staff_user is None:
        return None

    parsed = parse_staff_reply_text(text)
    if parsed is not None:
        conv_id, reply_body = parsed
        ok, status = submit_staff_reply_from_max(staff_user, conv_id, reply_body)
        return _send_to_user(user_key, status if ok else f"Не отправлено: {status}")

    raw = (text or "").strip().casefold()
    if raw.startswith("/reply"):
        return _send_to_user(user_key, compose_staff_reply_help())

    if resolve_menu_action(text) is not None:
        return None

    return _send_to_user(user_key, compose_staff_reply_help())


def _ingest_support_text(
    *,
    user_id: str,
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

    external_message_id = _message_external_id(message)
    try:
        conversation = get_or_create_messenger_conversation(
            Channel.MAX,
            user_id,
            display_name=display_name,
        )
        _inbound, auto = add_inbound_message(
            conversation,
            text,
            external_message_id=external_message_id,
            raw_payload={"max_mid": external_message_id},
            display_name=display_name,
        )
    except SupportChatError:
        logger.warning("max_support_ingest_rejected user_id=%s", user_id)
        return None

    if auto is not None:
        return _send_to_user(
            user_id,
            auto.body,
            attachments=main_menu_keyboard(),
        )
    return None


def _start_payload_from_update(update: dict[str, Any]) -> str:
    """Read deep-link payload from bot_started update when present."""
    for key in ("payload", "start_payload", "start"):
        raw = update.get(key)
        if isinstance(raw, str) and raw.strip():
            return resolve_start_action(raw.strip())
    return "start"


def _reply_for_action(action: str, user_key: str) -> tuple[str, list[dict[str, Any]] | None]:
    keyboard = main_menu_keyboard()
    if action in {"start", "help"}:
        return compose_welcome_text(), keyboard
    if action in {"contacts", "contact"}:
        return compose_contacts_text(), keyboard
    if action == "catalog":
        return compose_catalog_reply(), keyboard
    if action == "consultation":
        return compose_consultation_reply(), keyboard
    if action in {"where", "gdekupit", "where_to_buy"}:
        return compose_where_reply(), keyboard
    if action == "channel":
        return compose_channel_reply(), keyboard
    if action == "chatid":
        return compose_chatid_reply(user_key), keyboard
    return compose_fallback_reply(), keyboard


def _user_key_from_update(update: dict[str, Any]) -> str | None:
    """MAX user_id from bot_started / dialog_cleared and similar updates."""
    user = update.get("user")
    if isinstance(user, dict) and user.get("user_id") is not None:
        return str(user.get("user_id"))
    raw = update.get("user_id")
    if raw is not None:
        return str(raw)
    return None


def _handle_bot_started(update: dict[str, Any]) -> PublishResult | None:
    user_key = _user_key_from_update(update)
    if user_key is None:
        return None
    action = _start_payload_from_update(update)
    if action in {"start", "help"}:
        return _send_welcome_to_user(user_key, compose_welcome_text())
    return _send_reply_for_action(user_key, action)


def _handle_dialog_cleared(update: dict[str, Any]) -> PublishResult | None:
    """Re-send welcome when the user clears the 1:1 bot chat history."""
    user_key = _user_key_from_update(update)
    if user_key is None:
        return None
    return _send_welcome_to_user(user_key, compose_welcome_text())


def _handle_message_created(update: dict[str, Any]) -> PublishResult | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("sender")
    if not isinstance(sender, dict):
        return None
    if sender.get("is_bot"):
        return None
    recipient = message.get("recipient")
    if isinstance(recipient, dict):
        chat_type = (recipient.get("chat_type") or "").strip().casefold()
        if chat_type and chat_type != "dialog":
            return None
    user_id = sender.get("user_id")
    if user_id is None:
        return None
    text = _message_plain_text(message)
    if text is None:
        return None

    user_key = str(user_id)
    display_name = _display_name_from_user(sender)

    staff_reply = _try_staff_max_reply(user_key, text)
    if staff_reply is not None:
        return staff_reply

    action = resolve_menu_action(text)

    if action is not None:
        return _send_reply_for_action(user_key, action)

    return _ingest_support_text(
        user_id=user_key,
        text=text,
        message=message,
        display_name=display_name,
    )


def handle_max_update(update: dict[str, Any]) -> PublishResult | None:
    """Process one MAX Update object; send a reply when applicable."""
    if not isinstance(update, dict):
        return None
    update_type = (update.get("update_type") or "").strip()
    if update_type == "bot_started":
        return _handle_bot_started(update)
    if update_type == "dialog_cleared":
        return _handle_dialog_cleared(update)
    if update_type == "message_created":
        return _handle_message_created(update)
    return None
