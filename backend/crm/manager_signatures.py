"""Plain-text manager signatures for CRM lead replies."""

from __future__ import annotations

import re

from crm.email_body import is_html_email_body

_ASSISTANT_EMAIL = "assistant@hoocon.ru"

_EMAIL_LINE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Персональные контакты менеджеров по служебной почте — «профиль» подписи
# (staff User не хранит телефон; каноничный источник — этот словарь).
_MANAGER_CONTACTS: dict[str, dict[str, str]] = {
    _ASSISTANT_EMAIL: {
        "name": "Людмила",
        "company": 'ООО "ХОГОН"',
        "phone": "+7(995)780-70-18",
    },
}

_MANAGER_SIGNATURES: dict[str, str] = {
    email: f"С уважением, {c['name']}\n{c['company']}\n{c['phone']}\n{email}" for email, c in _MANAGER_CONTACTS.items()
}


def manager_reply_signature(manager_email: str) -> str:
    """Return a plain-text signature block for the manager mailbox, if configured."""
    key = (manager_email or "").strip().casefold()
    if not key:
        return ""
    return _MANAGER_SIGNATURES.get(key, "")


def manager_signature_contacts(manager_email: str) -> dict[str, str] | None:
    """Structured signature contacts (name/company/phone/email) for a manager.

    Args:
        manager_email: manager mailbox (login email on the staff user).

    Returns:
        Dict with ``name``/``company``/``phone``/``email``, or None when the
        mailbox is not configured in ``_MANAGER_CONTACTS``.
    """
    key = (manager_email or "").strip().casefold()
    if not key or key not in _MANAGER_CONTACTS:
        return None
    return {**_MANAGER_CONTACTS[key], "email": key}


def manager_reply_signature_html(manager_email: str) -> str:
    """HTML signature block for rich-text compose replies."""
    plain = manager_reply_signature(manager_email)
    if not plain:
        return ""
    lines: list[str] = []
    for line in plain.split("\n"):
        stripped = line.strip()
        if stripped.startswith("mailto:"):
            addr = stripped.removeprefix("mailto:")
            lines.append(f'<a href="mailto:{addr}">{addr}</a>')
            continue
        tel_match = re.search(r"^(?P<label>.+?)\s*\(tel:(?P<href>[^)]+)\)\s*$", stripped)
        if tel_match:
            label = tel_match.group("label").strip()
            href = tel_match.group("href").strip()
            lines.append(f'<a href="tel:{href}">{label}</a>')
            continue
        if _EMAIL_LINE.fullmatch(stripped):
            lines.append(f'<a href="mailto:{stripped}">{stripped}</a>')
            continue
        if stripped.startswith("+") and any(ch.isdigit() for ch in stripped):
            tel_href = "+" + re.sub(r"\D", "", stripped)
            lines.append(f'<a href="tel:{tel_href}">{stripped}</a>')
            continue
        lines.append(stripped)
    return "<br>".join(lines)


def assemble_lead_reply_body(body: str, manager_email: str) -> str:
    """Append manager signature and Reply-To hint to the composed reply body."""
    from crm.mail_links import lead_reply_footer, lead_reply_footer_html

    if is_html_email_body(body):
        text = (body or "").strip()
        signature = manager_reply_signature_html(manager_email)
        if signature:
            text = f"{text}<br><br>{signature}" if text else signature
        return text + lead_reply_footer_html(manager_email)

    text = (body or "").rstrip()
    signature = manager_reply_signature(manager_email)
    if signature:
        text = f"{text}\n\n{signature}" if text else signature
    return text + lead_reply_footer(manager_email)
