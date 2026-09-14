"""Celery tasks: MAX DMs to staff (managers + superusers)."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.max_staff")


@shared_task
def notify_staff_max_new_lead(lead_id: int) -> int:
    """MAX alert for new lead (RFQ / consultation / replacement)."""
    from accounts.max_alerts import (
        format_staff_max_message,
        send_max_to_users,
        staff_max_recipients_managers,
        staff_max_recipients_superusers,
    )
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_lead_push_copy

    site = SiteSettings.load()
    if not site.staff_max_leads_enabled:
        return 0
    try:
        lead = Lead.objects.select_related("assignee").get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title, body = staff_lead_push_copy(
        name=lead.name,
        lead_type=lead.get_lead_type_display(),
    )
    text = format_staff_max_message(
        title=title,
        body=body,
        url=f"/admin/leads/lead/{lead.pk}/change/",
    )
    managers = staff_max_recipients_managers(lead_assignee_id=lead.assignee_id)
    users = list(managers) + list(staff_max_recipients_superusers())
    sent = send_max_to_users(users, text)
    logger.info("max_staff_lead lead_id=%s sent=%s", lead_id, sent)
    return sent


@shared_task
def notify_staff_max_support(conversation_id: int) -> int:
    """MAX alert for inbound support message."""
    from accounts.max_alerts import (
        format_staff_max_message,
        send_max_to_users,
        staff_max_recipients_managers,
        staff_max_recipients_superusers,
    )
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_support_push_copy
    from supportchat.models import Conversation

    site = SiteSettings.load()
    if not site.staff_max_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    from supportchat.models import Message, MessageDirection

    label = conv.display_name or conv.get_channel_display()
    title, body = staff_support_push_copy(label=label)
    last_inbound = (
        Message.objects.filter(
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND,
        )
        .order_by("-id")
        .first()
    )
    if last_inbound is not None:
        snippet = (last_inbound.body or "").strip().replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:219].rstrip() + "…"
        if snippet:
            channel_label = conv.get_channel_display()
            body = f"{body}\n\n{channel_label}: {snippet}"
    text = format_staff_max_message(
        title=title,
        body=body,
        url=f"/admin/supportchat/conversation/{conv.pk}/change/",
    )
    users = list(staff_max_recipients_managers()) + list(staff_max_recipients_superusers())
    sent = send_max_to_users(users, text)
    logger.info("max_staff_support conv_id=%s sent=%s", conversation_id, sent)
    return sent
