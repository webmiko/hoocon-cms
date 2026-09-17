"""Manager reply links — Yandex Mail app first, web compose fallback."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode

_YANDEX_COMPOSE_RU = "https://mail.yandex.ru/compose"
_YANDEX_COMPOSE_COM = "https://mail.yandex.com/compose"
_YANDEX_MAIL_ANDROID_PACKAGE = "ru.yandex.mail"
_YANDEX_MAIL_APP_SCHEME = "yandexmail"


@dataclass(frozen=True, slots=True)
class LeadReplyEmailUrls:
    """URLs to open Yandex Mail app, with web compose as fallback."""

    web: str
    yandex_app: str
    yandex_android: str
    mailto: str


def yandex_compose_web_base_url(manager_email: str = "") -> str:
    """Pick Yandex Mail web host from the manager mailbox domain."""
    normalized = (manager_email or "").strip().casefold()
    if normalized.endswith("@yandex.com"):
        return _YANDEX_COMPOSE_COM
    return _YANDEX_COMPOSE_RU


def _compose_body(body: str = "", manager_email: str = "") -> str:
    """Optional body with manager mailbox hint (mailto has no reliable From)."""
    text = (body or "").strip()
    sender = (manager_email or "").strip()
    if sender:
        hint = f"Отправитель: {sender}"
        text = f"{hint}\n\n{text}" if text else hint
    return text


def build_yandex_compose_web_url(
    *,
    to: str,
    subject: str,
    body: str = "",
    from_email: str = "",
) -> str:
    """Yandex Mail web compose — fallback when the native app is absent."""
    recipient = (to or "").strip()
    if not recipient:
        return ""
    params: dict[str, str] = {
        "to": recipient,
        "subject": (subject or "").strip(),
    }
    full_body = _compose_body(body, from_email)
    if full_body:
        params["body"] = full_body
    sender = (from_email or "").strip()
    if sender:
        params["from"] = sender
    base = yandex_compose_web_base_url(sender)
    return f"{base}?{urlencode(params, quote_via=quote)}"


def build_mailto_compose_url(
    *,
    to: str,
    subject: str,
    body: str = "",
    manager_email: str = "",
) -> str:
    """mailto: for Android intent payload (ru.yandex.mail package)."""
    recipient = (to or "").strip()
    if not recipient:
        return ""
    params: list[tuple[str, str]] = []
    if (subject or "").strip():
        params.append(("subject", subject.strip()))
    full_body = _compose_body(body, manager_email)
    if full_body:
        params.append(("body", full_body))
    if not params:
        return f"mailto:{recipient}"
    return f"mailto:{recipient}?{urlencode(params, quote_via=quote)}"


def build_yandex_mail_app_url(
    *,
    to: str,
    subject: str,
    body: str = "",
    manager_email: str = "",
) -> str:
    """yandexmail:// deep link for the installed Yandex Mail app."""
    recipient = (to or "").strip()
    if not recipient:
        return ""
    params: dict[str, str] = {
        "to": recipient,
        "subject": (subject or "").strip(),
    }
    full_body = _compose_body(body, manager_email)
    if full_body:
        params["body"] = full_body
    return f"{_YANDEX_MAIL_APP_SCHEME}://compose?{urlencode(params, quote_via=quote)}"


def build_yandex_mail_android_intent_url(mailto_url: str) -> str:
    """Android intent opens ru.yandex.mail even when it is not the default MUA."""
    mailto = (mailto_url or "").strip()
    if not mailto.startswith("mailto:"):
        return ""
    return f"intent:{mailto}#Intent;scheme=mailto;package={_YANDEX_MAIL_ANDROID_PACKAGE};end"


def build_lead_reply_email_urls(
    *,
    lead_email: str,
    subject: str,
    manager_email: str = "",
    body: str = "",
) -> LeadReplyEmailUrls:
    """Reply to an RFQ/lead: native Yandex Mail app, else web compose."""
    mailto = build_mailto_compose_url(
        to=lead_email,
        subject=subject,
        body=body,
        manager_email=manager_email,
    )
    return LeadReplyEmailUrls(
        web=build_yandex_compose_web_url(
            to=lead_email,
            subject=subject,
            body=body,
            from_email=manager_email,
        ),
        yandex_app=build_yandex_mail_app_url(
            to=lead_email,
            subject=subject,
            body=body,
            manager_email=manager_email,
        ),
        yandex_android=build_yandex_mail_android_intent_url(mailto),
        mailto=mailto,
    )


def build_lead_reply_email_url(
    *,
    lead_email: str,
    subject: str,
    manager_email: str = "",
) -> str:
    """Web compose URL for inline list links (no JS app-try on changelist)."""
    return build_yandex_compose_web_url(
        to=lead_email,
        subject=subject,
        from_email=manager_email,
    )
