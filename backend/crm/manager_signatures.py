"""Plain-text manager signatures for CRM lead replies."""

from __future__ import annotations

import re

from crm.email_body import is_html_email_body

_ASSISTANT_EMAIL = "assistant@hoocon.ru"

_LUDMILA_SIGNATURE = 'С уважением, Людмила\nООО "ХОГОН"\n+7(995)780-70-18\nassistant@hoocon.ru'

_EMAIL_LINE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MANAGER_SIGNATURES: dict[str, str] = {
    _ASSISTANT_EMAIL: _LUDMILA_SIGNATURE,
}


def manager_reply_signature(manager_email: str) -> str:
    """Return a plain-text signature block for the manager mailbox, if configured."""
    key = (manager_email or "").strip().casefold()
    if not key:
        return ""
    return _MANAGER_SIGNATURES.get(key, "")


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
