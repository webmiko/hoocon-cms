"""Private chat attachment URLs (not public MEDIA)."""

from __future__ import annotations

from django.urls import reverse

from supportchat.models import Message


def message_attachment_url(message: Message) -> str:
    """Relative API path that checks widget session or staff perm.

    Args:
        message: persisted Message with an attachment.

    Returns:
        URL path, or empty string when there is no file.
    """
    if not message.pk or not message.attachment:
        return ""
    return reverse("support-message-attachment", args=[message.pk])
