"""Celery tasks: Telegram DMs to staff (managers + superusers)."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.telegram_staff")


@shared_task
def notify_staff_telegram_new_lead(lead_id: int) -> int:
    """Telegram fallback for new lead when the recipient has no Web Push."""
    from accounts.telegram_alerts import (
        format_staff_telegram_message,
        send_telegram_to_users,
        staff_telegram_recipients_managers,
        staff_telegram_recipients_superusers,
        without_staff_webpush,
    )
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_lead_push_copy

    site = SiteSettings.load()
    if not site.staff_telegram_leads_enabled:
        return 0
    try:
        lead = Lead.objects.select_related("assignee").get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title, body = staff_lead_push_copy(
        name=lead.name,
        lead_type=lead.get_lead_type_display(),
    )
    text = format_staff_telegram_message(
        title=title,
        body=body,
        url=f"/admin/leads/lead/{lead.pk}/change/",
    )
    managers = staff_telegram_recipients_managers(lead_assignee_id=lead.assignee_id)
    users = without_staff_webpush(
        list(managers) + list(staff_telegram_recipients_superusers()),
    )
    sent = send_telegram_to_users(users, text)
    logger.info("telegram_staff_lead lead_id=%s sent=%s", lead_id, sent)
    return sent


@shared_task
def notify_staff_telegram_support(conversation_id: int) -> int:
    """Telegram fallback for inbound support when the recipient has no Web Push."""
    from accounts.telegram_alerts import (
        format_staff_telegram_message,
        send_telegram_to_users,
        staff_telegram_recipients_managers,
        staff_telegram_recipients_superusers,
        without_staff_webpush,
    )
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_support_push_copy
    from supportchat.models import Conversation

    site = SiteSettings.load()
    if not site.staff_telegram_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    label = conv.display_name or conv.get_channel_display()
    title, body = staff_support_push_copy(label=label)
    text = format_staff_telegram_message(
        title=title,
        body=body,
        url=f"/admin/supportchat/conversation/{conv.pk}/change/",
    )
    users = without_staff_webpush(
        list(staff_telegram_recipients_managers()) + list(staff_telegram_recipients_superusers()),
    )
    sent = send_telegram_to_users(users, text)
    logger.info("telegram_staff_support conv_id=%s sent=%s", conversation_id, sent)
    return sent


@shared_task
def notify_superuser_telegram_crm(title: str, body: str, url: str = "") -> int:
    """Telegram fallback for CRM changes when the superuser has no Web Push."""
    from accounts.telegram_alerts import (
        format_staff_telegram_message,
        send_telegram_to_users,
        staff_telegram_recipients_superusers,
        without_staff_webpush,
    )
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    if not site.staff_telegram_superuser_crm_enabled:
        return 0
    text = format_staff_telegram_message(title=title, body=body, url=url)
    users = without_staff_webpush(staff_telegram_recipients_superusers())
    sent = send_telegram_to_users(users, text)
    logger.info("telegram_superuser_crm sent=%s title=%s", sent, title[:40])
    return sent
