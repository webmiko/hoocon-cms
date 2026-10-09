"""Manager signatures for CRM lead replies (plain text and HTML)."""

from __future__ import annotations

import re
from html import escape

from django.conf import settings

from crm.email_body import is_html_email_body


def _contacts_by_email() -> dict[str, dict[str, str]]:
    """``settings.MANAGER_SIGNATURE_CONTACTS`` keyed by casefolded mailbox."""
    raw = getattr(settings, "MANAGER_SIGNATURE_CONTACTS", None) or {}
    return {str(email).strip().casefold(): dict(contact) for email, contact in raw.items()}


def manager_signature_contacts(manager_email: str) -> dict[str, str] | None:
    """Structured signature contacts (name/company/phone/email) for a manager.

    Args:
        manager_email: manager mailbox (login email on the staff user).

    Returns:
        Dict with ``name``/``company``/``phone``/``email``, or None when the
        mailbox has no entry in ``settings.MANAGER_SIGNATURE_CONTACTS``.
    """
    key = (manager_email or "").strip().casefold()
    contact = _contacts_by_email().get(key) if key else None
    if contact is None:
        return None
    return {
        "name": contact.get("name", ""),
        "company": contact.get("company", ""),
        "phone": contact.get("phone", ""),
        "email": key,
    }


def manager_reply_signature(manager_email: str) -> str:
    """Return a plain-text signature block for the manager mailbox, if configured."""
    contact = manager_signature_contacts(manager_email)
    if contact is None:
        return ""
    lines = [f"С уважением, {contact['name']}", contact["company"], contact["phone"], contact["email"]]
    return "\n".join(line for line in lines if line)


def manager_reply_signature_html(manager_email: str) -> str:
    """HTML signature block for rich-text compose replies (tel/mailto links)."""
    contact = manager_signature_contacts(manager_email)
    if contact is None:
        return ""
    lines = [escape(f"С уважением, {contact['name']}", quote=False)]
    if contact["company"]:
        lines.append(escape(contact["company"], quote=False))
    if contact["phone"]:
        tel_href = "+" + re.sub(r"\D", "", contact["phone"])
        lines.append(f'<a href="tel:{tel_href}">{escape(contact["phone"], quote=False)}</a>')
    email = escape(contact["email"])
    lines.append(f'<a href="mailto:{email}">{email}</a>')
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
