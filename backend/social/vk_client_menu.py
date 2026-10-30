"""Client menu keyboards for VK (links mirror MAX bot menu)."""

from __future__ import annotations

from django.conf import settings

from social.copy import site_page
from social.max_bot import (
    BTN_CATALOG,
    BTN_COMPANY,
    BTN_CONSULTATION,
    BTN_CONTACTS,
    BTN_DOCS,
    BTN_FAQ,
    BTN_PRIVACY,
    BTN_TERMS,
    BTN_WHERE,
)
from social.vk_keyboard import vk_inline_keyboard


def _vk_community_url() -> str:
    name = getattr(settings, "VK_COMMUNITY_SCREEN_NAME", "hoocon_russia").strip().lstrip("@")
    return f"https://vk.ru/{name or 'hoocon_russia'}"


def main_menu_keyboard_vk() -> str:
    """Inline link keyboard under welcome / auto-replies."""
    return vk_inline_keyboard(
        [
            [
                {"type": "link", "text": BTN_CATALOG, "url": site_page("/catalog")},
                {"type": "link", "text": BTN_CONSULTATION, "url": site_page("/consultation")},
            ],
            [
                {"type": "link", "text": BTN_WHERE, "url": site_page("/gde-kupit")},
                {"type": "link", "text": BTN_CONTACTS, "url": site_page("/kontakty")},
            ],
            [
                {"type": "link", "text": BTN_DOCS, "url": site_page("/dokumentaciya")},
                {"type": "link", "text": BTN_FAQ, "url": site_page("/faq")},
            ],
            [
                {"type": "link", "text": "Сообщество VK", "url": _vk_community_url()},
                {"type": "link", "text": BTN_COMPANY, "url": site_page("/company")},
            ],
            [
                # VK: max 5 rows; open_link row — не более 2 кнопок (3 → invalid).
                {"type": "link", "text": BTN_PRIVACY, "url": site_page("/privacy-policy")},
                {"type": "link", "text": BTN_TERMS, "url": site_page("/terms")},
            ],
        ],
    )
