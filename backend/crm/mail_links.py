"""Manager reply links — Yandex Mail web compose (not system mail client)."""

from __future__ import annotations

from urllib.parse import quote, urlencode

_YANDEX_COMPOSE_RU = "https://mail.yandex.ru/compose"
_YANDEX_COMPOSE_COM = "https://mail.yandex.com/compose"


def yandex_compose_base_url(manager_email: str = "") -> str:
    """Pick Yandex Mail host from the manager mailbox domain."""
    normalized = (manager_email or "").strip().casefold()
    if normalized.endswith("@yandex.com"):
        return _YANDEX_COMPOSE_COM
    return _YANDEX_COMPOSE_RU


def build_yandex_compose_url(
    *,
    to: str,
    subject: str,
    body: str = "",
    from_email: str = "",
) -> str:
    """Yandex Mail web compose — opens in browser, not the default MUA."""
    recipient = (to or "").strip()
    if not recipient:
        return ""
    params: dict[str, str] = {
        "to": recipient,
        "subject": (subject or "").strip(),
    }
    if body.strip():
        params["body"] = body.strip()
    sender = (from_email or "").strip()
    if sender:
        params["from"] = sender
    base = yandex_compose_base_url(sender)
    return f"{base}?{urlencode(params, quote_via=quote)}"


def build_lead_reply_email_url(
    *,
    lead_email: str,
    subject: str,
    manager_email: str = "",
) -> str:
    """Reply to an RFQ/lead client from the manager profile mailbox."""
    return build_yandex_compose_url(
        to=lead_email,
        subject=subject,
        from_email=manager_email,
    )
