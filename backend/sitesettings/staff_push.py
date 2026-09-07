"""Staff browser-notification template helpers (SiteSettings)."""

from __future__ import annotations

_DEFAULT_LEAD_TITLE = "Новая заявка"
_DEFAULT_LEAD_BODY = "{имя}: {тип}"
_DEFAULT_SUPPORT_TITLE = "Новое сообщение в поддержке"
_DEFAULT_SUPPORT_BODY = "{метка}: новое обращение"


def render_push_template(template: str, *, fallback: str, **vars: str) -> str:
    """Replace ``{key}`` placeholders; empty template uses ``fallback``.

    Unknown braces are left as-is. Values are inserted as plain text.
    """
    text = (template or "").strip() or fallback
    for key, value in vars.items():
        text = text.replace("{" + key + "}", value)
    return text


def staff_lead_push_copy(*, name: str, lead_type: str) -> tuple[str, str]:
    """Title/body for a new-lead staff push from SiteSettings."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    title = render_push_template(
        site.staff_push_lead_title,
        fallback=_DEFAULT_LEAD_TITLE,
    )
    body = render_push_template(
        site.staff_push_lead_body,
        fallback=_DEFAULT_LEAD_BODY,
        name=name,
        lead_type=lead_type,
        **{"имя": name, "тип": lead_type},
    )
    return title, body


def staff_support_push_copy(*, label: str) -> tuple[str, str]:
    """Title/body for an inbound-support staff push from SiteSettings."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    title = render_push_template(
        site.staff_push_support_title,
        fallback=_DEFAULT_SUPPORT_TITLE,
    )
    body = render_push_template(
        site.staff_push_support_body,
        fallback=_DEFAULT_SUPPORT_BODY,
        label=label,
        **{"метка": label},
    )
    return title, body
