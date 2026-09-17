"""MAX bot profile (PATCH /me): description, avatar and command menu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from social.copy import hours_and_phone_line
from social.max_bot import BOT_COMMANDS, max_bot_username, max_channel_deep_link
from social.max_channel import channel_cover_path
from social.max_http import max_json_request, max_upload_image

_BOT_DISPLAY_NAME = "Hoocon"


def bot_display_name() -> str:
    """Public bot title in MAX (≤64 chars)."""
    return _BOT_DISPLAY_NAME


def bot_description() -> str:
    """Bot profile description shown before the dialog opens."""
    bot = max_bot_username()
    text = (
        "Официальный бот Hoocon — электроприводы и арматура для вентиляции и ОВК.\n\n"
        "• каталог и подбор аналогов Belimo\n"
        "• заявка и коммерческое предложение\n"
        "• ответы менеджера в рабочие дни\n\n"
        f"Команда /start — меню с кнопками.\n"
        f"Канал новостей: {max_channel_deep_link()}\n"
        f"Бот: @{bot} · hoocon.ru\n"
        f"Режим ответа: {hours_and_phone_line()}"
    )
    return text[:16000]


def bot_commands_payload() -> list[dict[str, str]]:
    """Public slash-command hints for MAX client menu (staff /chatid excluded)."""
    return [{"name": row["command"], "description": row["description"]} for row in BOT_COMMANDS]


_BOT_AVATAR_STATIC = Path("static/social/max-bot-avatar.png")


def bot_avatar_path() -> Path | None:
    """Local bot profile avatar (square logo; channel cover is separate)."""
    configured = getattr(settings, "MAX_BOT_AVATAR_PATH", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    base = Path(settings.BASE_DIR)
    candidates.append(base / _BOT_AVATAR_STATIC)
    for path in candidates:
        if path.is_file():
            return path
    return channel_cover_path()


def patch_bot_profile(
    token: str,
    *,
    image_token: str | None = None,
    notify: bool = False,
) -> tuple[int, dict[str, Any]]:
    """PATCH /me — bot title, description, avatar and commands."""
    body: dict[str, Any] = {
        "name": bot_display_name(),
        "description": bot_description(),
        "commands": bot_commands_payload(),
        "notify": notify,
    }
    if image_token:
        body["photo"] = {"token": image_token}
    return max_json_request("PATCH", "/me", token, payload=body)


def get_bot_profile(token: str) -> tuple[int, dict[str, Any]]:
    """GET /me — current bot profile."""
    return max_json_request("GET", "/me", token)


def setup_bot(
    token: str,
    *,
    notify_profile: bool = False,
) -> dict[str, str]:
    """Bootstrap bot profile: avatar, description and command menu."""
    cover = bot_avatar_path()
    image_token = max_upload_image(token, cover) if cover else None

    status, data = patch_bot_profile(
        token,
        image_token=image_token,
        notify=notify_profile,
    )
    if status >= 400:
        raise RuntimeError(f"PATCH /me failed: HTTP {status} {data!r}")

    return {
        "name": bot_display_name(),
        "profile_status": str(status),
        "avatar": str(cover) if cover else "",
        "commands": str(len(bot_commands_payload())),
    }
