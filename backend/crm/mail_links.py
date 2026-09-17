"""Manager reply links — Yandex Mail app first, web compose fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from leads.models import Lead

_YANDEX_COMPOSE_RU = "https://mail.yandex.ru/compose"
_YANDEX_COMPOSE_COM = "https://mail.yandex.com/compose"
_YANDEX_MAIL_ANDROID_PACKAGE = "ru.yandex.mail"


@dataclass(frozen=True, slots=True)
class LeadReplyEmailUrls:
    """URLs to open Yandex Mail app, with web compose as fallback."""

    web: str
    mailto: str
    yandex_android: str


def yandex_compose_web_base_url(manager_email: str = "") -> str:
    """Pick Yandex Mail web host from the manager mailbox domain."""
    normalized = (manager_email or "").strip().casefold()
    if normalized.endswith("@yandex.com"):
        return _YANDEX_COMPOSE_COM
    return _YANDEX_COMPOSE_RU


def format_lead_reply_subject(lead: Lead) -> str:
    """Default KP reply subject for a lead."""
    company = (lead.company or "").strip() or "клиент"
    return f"КП #{lead.pk} — {company}"


def staff_reply_to_email(user: AbstractBaseUser | None) -> str:
    """Manager mailbox for Reply-To from an authenticated staff user."""
    if user is None or getattr(user, "is_anonymous", True):
        return ""
    return (getattr(user, "email", "") or "").strip()


def lead_reply_footer(manager_email: str) -> str:
    """Plain-text hint appended to outbound KP replies."""
    email = (manager_email or "").strip()
    if not email:
        return "\n\n--\nОтветьте на это письмо — ответ придёт менеджеру, который отправил КП."
    return f"\n\n--\nОтветьте на это письмо — ваш ответ придёт на {email}."


def lead_reply_footer_html(manager_email: str) -> str:
    """HTML hint appended to rich-text KP replies."""
    plain = lead_reply_footer(manager_email).strip()
    if not plain:
        return ""
    if plain.startswith("--"):
        hint = plain.removeprefix("--").strip()
        return (
            '<br><br><hr style="border:0;border-top:1px solid #d1d1d6;margin:1rem 0">'
            f'<p style="margin:0;color:#6e6e73;font-size:0.85em;line-height:1.45">{hint}</p>'
        )
    return f"<br><br><p>{plain}</p>"


def format_lead_reply_body(lead: Lead) -> str:
    """Plain-text KP reply body: client comment + SKU lines from the lead."""
    parts: list[str] = []
    message = (lead.message or "").strip()
    if message:
        parts.append(message)

    item_lines: list[str] = []
    items = list(lead.items.order_by("sort_order", "id"))
    if not items and lead.sku_id:
        sku = getattr(lead, "sku", None)
        code = (getattr(sku, "sku_code", "") or "").strip()
        if code:
            qty = lead.quantity or 1
            item_lines.append(f"- {code} × {qty}")
    else:
        for item in items:
            code = (item.sku_code or "").strip()
            if not code and item.sku_id:
                sku = getattr(item, "sku", None)
                code = (getattr(sku, "sku_code", "") or "").strip()
            if not code:
                code = "?"
            qty = item.quantity or 1
            item_lines.append(f"- {code} × {qty}")

    if item_lines:
        if parts:
            parts.append("")
        parts.append("Позиции по заявке:")
        parts.extend(item_lines)

    return "\n".join(parts)


def build_mailto_compose_url(
    *,
    to: str,
    subject: str,
    body: str = "",
) -> str:
    """mailto: opens Yandex Mail / other MUAs with to, subject and body prefilled."""
    recipient = (to or "").strip()
    if not recipient:
        return ""
    params: list[tuple[str, str]] = []
    if (subject or "").strip():
        params.append(("subject", subject.strip()))
    if (body or "").strip():
        params.append(("body", body.strip()))
    if not params:
        return f"mailto:{recipient}"
    return f"mailto:{recipient}?{urlencode(params, quote_via=quote)}"


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
    # Yandex mailto handler passes the full mailto:…?subject&body link in ``mailto=``.
    inner_mailto = build_mailto_compose_url(
        to=recipient,
        subject=subject,
        body=body,
    )
    params: dict[str, str] = {
        "mailto": inner_mailto,
    }
    if (subject or "").strip():
        params["subject"] = subject.strip()
    if (body or "").strip():
        params["body"] = body.strip()
    sender = (from_email or "").strip()
    if sender:
        params["from"] = sender
    base = yandex_compose_web_base_url(sender)
    return f"{base}?{urlencode(params, quote_via=quote)}"


def build_yandex_mail_android_intent_url(mailto_url: str) -> str:
    """Android intent opens ru.yandex.mail with a prefilled mailto compose."""
    mailto = (mailto_url or "").strip()
    if not mailto.startswith("mailto:"):
        return ""
    return (
        f"intent:{mailto}#Intent;"
        f"action=android.intent.action.SENDTO;"
        f"scheme=mailto;"
        f"package={_YANDEX_MAIL_ANDROID_PACKAGE};end"
    )


def build_lead_reply_email_urls(
    *,
    lead_email: str,
    subject: str,
    manager_email: str = "",
    body: str = "",
) -> LeadReplyEmailUrls:
    """Reply to an RFQ/lead: mailto for Yandex Mail app, else web compose."""
    mailto = build_mailto_compose_url(
        to=lead_email,
        subject=subject,
        body=body,
    )
    return LeadReplyEmailUrls(
        web=build_yandex_compose_web_url(
            to=lead_email,
            subject=subject,
            body=body,
            from_email=manager_email,
        ),
        mailto=mailto,
        yandex_android=build_yandex_mail_android_intent_url(mailto),
    )


def build_lead_reply_email_url(
    *,
    lead_email: str,
    subject: str,
    manager_email: str = "",
    body: str = "",
) -> str:
    """Web compose URL for inline list links (no JS app-try on changelist)."""
    return build_yandex_compose_web_url(
        to=lead_email,
        subject=subject,
        body=body,
        from_email=manager_email,
    )
