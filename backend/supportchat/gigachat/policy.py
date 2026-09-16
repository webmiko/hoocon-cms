"""When the GigaChat assistant may reply."""

from __future__ import annotations

from sitesettings.credentials import gigachat_credentials
from sitesettings.models import SiteSettings
from supportchat.models import Conversation


def ai_assistant_enabled() -> bool:
    """Global toggle + credentials present."""
    site = SiteSettings.load()
    return bool(site.gigachat_enabled and gigachat_credentials(site))


def conversation_ai_eligible(conversation: Conversation) -> bool:
    """Thread is still handled by the bot."""
    return bool(
        conversation.ai_active and conversation.ai_escalated_at is None and conversation.assignee_id is None,
    )


def ai_max_turns() -> int:
    """Configured assistant turn limit."""
    from supportchat.gigachat.triage import is_triage_mode

    site = SiteSettings.load()
    configured = max(1, int(site.ai_max_turns or 5))
    if is_triage_mode():
        return min(configured, 4)
    return configured


def resolve_gigachat_model() -> str:
    """Model id from Admin or Django settings."""
    from django.conf import settings as dj_settings

    site = SiteSettings.load()
    model = (site.gigachat_model or "").strip()
    if model:
        return model
    return getattr(dj_settings, "GIGACHAT_MODEL", "GigaChat-2").strip()
