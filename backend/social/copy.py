"""Shared site copy for messenger bots (Telegram, MAX).

Single source for contacts/requisites aligned with seed_site_content and /kontakty.
"""

from __future__ import annotations

import html

from django.conf import settings

# Site copy (aligned with seed_site_content / WhereToBuyPage).
PHONE = "8 800 350-58-98"
EMAIL_SALES = "sales@hoocon.ru"
EMAIL_INFO = "info@hoocon.ru"
HOURS = "Пн–Пт 9:30–17:30 (МСК), сб–вс — выходной"
ADDRESS = "143440, Московская область, г. о. Красногорск, пгт Путилково, тер. Гринвуд, стр. 7, помещ. 98 (3-й этаж)"
INN = "5024199634"
KPP = "502401001"
OGRN = "1195081070986"
BANK = "р/с 40702810838000199148, к/с 30101810400000000225, БИК 044525225, ПАО Сбербанк"


def site_url() -> str:
    return getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")


def site_page(path: str) -> str:
    base = site_url()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def hours_and_phone_line() -> str:
    return f"{HOURS} · {PHONE}"


def compose_contacts_plain(*, limit: int | None = None) -> str:
    """Contacts + requisites (plain text, e.g. MAX)."""
    text = (
        "Контакты ООО «Хогон» (бренд Hoocon)\n"
        "Ответим до 2 рабочих часов в рабочие дни.\n\n"
        f"Телефон: {PHONE}\n"
        f"Продажи: {EMAIL_SALES}\n"
        f"Сотрудничество / ПДн: {EMAIL_INFO}\n"
        f"Адрес: {ADDRESS}\n"
        f"Режим: {HOURS}\n\n"
        f"ИНН {INN}, КПП {KPP}, ОГРН {OGRN}\n"
        f"{BANK}\n\n"
        f"Полная страница: {site_url()}/kontakty"
    )
    return clip_text(text, limit) if limit is not None else text


def compose_contacts_html(*, limit: int | None = None) -> str:
    """Contacts + requisites (Telegram HTML subset)."""
    site = site_url()
    text = (
        "<b>Контакты ООО «Хогон»</b> (бренд Hoocon)\n"
        "Ответим до 2 рабочих часов в рабочие дни.\n\n"
        f"<b>Телефон:</b> {html.escape(PHONE)}\n"
        f"<b>Продажи:</b> {html.escape(EMAIL_SALES)}\n"
        f"<b>Сотрудничество / ПДн:</b> {html.escape(EMAIL_INFO)}\n"
        f"<b>Адрес:</b> {html.escape(ADDRESS)}\n"
        f"<b>Режим:</b> {html.escape(HOURS)}\n\n"
        "<b>Реквизиты</b>\n"
        f"ИНН {INN}, КПП {KPP}, ОГРН {OGRN}\n"
        f"{html.escape(BANK)}\n\n"
        f"Полная страница: {html.escape(site)}/kontakty"
    )
    return clip_text(text, limit) if limit is not None else text
