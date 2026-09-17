"""Plain-text manager signatures for CRM lead replies."""

from __future__ import annotations

_ASSISTANT_EMAIL = "assistant@hoocon.ru"

_LUDMILA_SIGNATURE = (
    'С уважением, Людмила\nООО "ХОГОН"\n+7(995)780-70-18 (tel:+7(995)780-70-18)\nmailto:assistant@hoocon.ru'
)

_MANAGER_SIGNATURES: dict[str, str] = {
    _ASSISTANT_EMAIL: _LUDMILA_SIGNATURE,
}


def manager_reply_signature(manager_email: str) -> str:
    """Return a plain-text signature block for the manager mailbox, if configured."""
    key = (manager_email or "").strip().casefold()
    if not key:
        return ""
    return _MANAGER_SIGNATURES.get(key, "")


def assemble_lead_reply_body(body: str, manager_email: str) -> str:
    """Append manager signature and Reply-To hint to the composed reply body."""
    from crm.mail_links import lead_reply_footer

    text = (body or "").rstrip()
    signature = manager_reply_signature(manager_email)
    if signature:
        text = f"{text}\n\n{signature}" if text else signature
    return text + lead_reply_footer(manager_email)
