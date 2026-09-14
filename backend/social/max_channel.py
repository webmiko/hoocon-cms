"""MAX channel profile text, welcome post and setup helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from social.max_bot import (
    BTN_CATALOG,
    BTN_COMPANY,
    BTN_CONSULTATION,
    BTN_CONTACTS,
    BTN_DOCS,
    BTN_FAQ,
    BTN_WHERE,
    _clip,
    max_bot_deep_link,
    max_bot_username,
)
from social.max_http import max_json_request, max_upload_image
from social.publishers import PublishResult, publish_max
from social.telegram_bot import _HOURS, _PHONE

_CHANNEL_TITLE = "Hoocon — электроприводы ОВК"
_WELCOME_STATIC = Path("static/social/telegram-welcome.webp")
_MESSAGE_MAX = 4000


def channel_title() -> str:
    """Public channel title."""
    return _CHANNEL_TITLE


def channel_description() -> str:
    """Channel about text (≤16000 chars)."""
    bot = max_bot_username()
    return (
        "Официальный канал ООО «Хогон» (бренд Hoocon).\n\n"
        "Электроприводы и арматура для вентиляции и ОВК:\n"
        "• новости каталога и наличие\n"
        "• подбор аналогов Belimo\n"
        "• статьи, документация и анонсы\n\n"
        f"Сайт hoocon.ru · Бот @{bot}\n"
        f"Поддержка в боте: {max_bot_deep_link('support')}"
    )


def channel_welcome_text() -> str:
    """Pinned welcome post in the channel."""
    text = (
        "Добро пожаловать в официальный канал Hoocon!\n\n"
        "Здесь — новости бренда, анонсы каталога, статьи по подбору "
        "электроприводов и арматуры для ОВК.\n\n"
        f"Вопросы и заявки — в боте @{max_bot_username()} "
        f"({max_bot_deep_link('support')}).\n"
        f"Режим ответа: {_HOURS} · {_PHONE}"
    )
    return _clip(text, _MESSAGE_MAX)


def channel_welcome_keyboard() -> list[dict[str, Any]]:
    """Inline buttons under the channel welcome post."""
    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")

    def link(text: str, url: str) -> dict[str, str]:
        return {"type": "link", "text": text, "url": url}

    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        link(BTN_CATALOG, f"{site}/catalog"),
                        link(BTN_CONSULTATION, f"{site}/consultation"),
                    ],
                    [
                        link(BTN_WHERE, f"{site}/gde-kupit"),
                        link(BTN_CONTACTS, f"{site}/kontakty"),
                    ],
                    [
                        link(BTN_DOCS, f"{site}/dokumentaciya"),
                        link(BTN_FAQ, f"{site}/faq"),
                    ],
                    [
                        link("Написать в бот", max_bot_deep_link("support")),
                        link(BTN_COMPANY, f"{site}/company"),
                    ],
                ],
            },
        },
    ]


def channel_cover_path() -> Path | None:
    """Local cover reused from Telegram welcome asset."""
    configured = getattr(settings, "MAX_CHANNEL_COVER_PATH", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    base = Path(settings.BASE_DIR)
    candidates.append(base / _WELCOME_STATIC)
    for path in candidates:
        if path.is_file():
            return path
    return None


def channel_icon_payload(token: str) -> dict[str, str]:
    """PATCH /chats icon body from uploaded image token."""
    return {"token": token}


def setup_channel_profile(
    token: str,
    chat_id: str,
    *,
    image_token: str | None = None,
    notify: bool = False,
) -> tuple[int, dict[str, Any]]:
    """PATCH channel title, description and optional icon."""
    body: dict[str, Any] = {
        "title": channel_title(),
        "description": channel_description(),
        "notify": notify,
    }
    if image_token:
        body["icon"] = channel_icon_payload(image_token)
    return max_json_request("PATCH", f"/chats/{chat_id}", token, payload=body)


def publish_channel_welcome(
    chat_id: str,
    *,
    image_token: str | None = None,
) -> PublishResult:
    """Post welcome message with cover and buttons to the channel."""
    attachments: list[dict[str, Any]] = list(channel_welcome_keyboard())
    if image_token:
        attachments.insert(0, {"type": "image", "payload": {"token": image_token}})
    return publish_max(
        chat_id=chat_id,
        text=channel_welcome_text(),
        attachments=attachments,
    )


def pin_channel_message(token: str, chat_id: str, message_id: str) -> tuple[int, dict[str, Any]]:
    """Pin welcome post in the channel."""
    return max_json_request(
        "PUT",
        f"/chats/{chat_id}/pin",
        token,
        payload={"message_id": message_id, "notify": False},
    )


def setup_channel(
    token: str,
    chat_id: str,
    *,
    pin_welcome: bool = True,
    notify_profile: bool = False,
) -> dict[str, str]:
    """Full channel bootstrap: profile, welcome post, optional pin."""
    cover = channel_cover_path()
    image_token = max_upload_image(token, cover) if cover else None

    profile_status, profile_data = setup_channel_profile(
        token,
        chat_id,
        image_token=image_token,
        notify=notify_profile,
    )
    if profile_status >= 400:
        raise RuntimeError(f"PATCH /chats failed: HTTP {profile_status} {profile_data!r}")

    post = publish_channel_welcome(chat_id, image_token=image_token)
    if not post.ok:
        raise RuntimeError(f"welcome post failed: {post.error}")

    mid = post.external_id
    if pin_welcome and mid:
        pin_status, pin_data = pin_channel_message(token, chat_id, mid)
        if pin_status >= 400:
            raise RuntimeError(f"PUT /chats/pin failed: HTTP {pin_status} {pin_data!r}")

    return {
        "chat_id": chat_id,
        "profile_status": str(profile_status),
        "welcome_mid": mid,
        "cover": str(cover) if cover else "",
    }
