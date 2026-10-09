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
def notify_staff_max_support(conversation_id: int, inbound_message_id: int | None = None) -> int:
    """MAX alert for inbound support message."""
    from accounts.max_alerts import (
        compose_staff_max_support_alert,
        format_staff_max_message,
        send_max_to_users,
        staff_max_recipients_managers,
        staff_max_recipients_superusers,
    )
    from sitesettings.models import SiteSettings
    from supportchat.models import Conversation
    from supportchat.services import claim_staff_support_push, inbound_superseded

    if inbound_message_id is not None and inbound_superseded(
        conversation_id,
        inbound_message_id,
    ):
        return 0
    site = SiteSettings.load()
    if not site.staff_max_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if not claim_staff_support_push("max", conv.pk, inbound_message_id):
        return 0
    title, body = compose_staff_max_support_alert(
        conv,
        inbound_message_id=inbound_message_id,
    )
    text = format_staff_max_message(
        title=title,
        body=body,
        url=f"/admin/supportchat/conversation/{conv.pk}/change/",
    )
    from social.max_staff_reply import (
        staff_support_alert_attachments,
        store_support_alert_mid,
    )

    attachments = staff_support_alert_attachments(conv.pk)
    users = list(staff_max_recipients_managers()) + list(staff_max_recipients_superusers())
    mids: dict[str, str] = {}
    sent = send_max_to_users(users, text, attachments=attachments, mids_out=mids)
    for uid, mid in mids.items():
        store_support_alert_mid(conv.pk, uid, mid, text)
    logger.info("max_staff_support conv_id=%s sent=%s", conversation_id, sent)
    return sent


@shared_task
def retire_max_support_alert(conversation_id: int, author_user_id: int | None = None) -> int:
    """Edit staff MAX alerts after a reply: drop «Ответить», mark who answered."""
    from accounts.max_alerts import (
        max_user_id_for,
        staff_max_recipients_managers,
        staff_max_recipients_superusers,
    )
    from social.max_staff_reply import load_support_alert_mid
    from social.publishers import edit_max_message
    from supportchat.models import Conversation
    from supportchat.presentation import staff_public_name

    try:
        conv = Conversation.objects.select_related("assignee").get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if author_user_id is None and conv.assignee_id is not None:
        author_user_id = conv.assignee_id
    author = None
    if author_user_id is not None:
        from django.contrib.auth import get_user_model

        author = get_user_model().objects.filter(pk=author_user_id).first()
    author_name = staff_public_name(author)

    users = list(staff_max_recipients_managers()) + list(staff_max_recipients_superusers())
    edited = 0
    for user in users:
        uid = max_user_id_for(user)
        if not uid:
            continue
        stored = load_support_alert_mid(conv.pk, uid)
        if not stored or not stored.get("mid"):
            continue
        base_text = stored.get("text") or ""
        suffix = "✅ Вы ответили" if author is not None and user.pk == author.pk else f"✅ Ответил: {author_name}"
        edit_max_message(
            stored["mid"],
            text=f"{base_text}\n\n{suffix}",
            attachments=[],
        )
        edited += 1
    if edited:
        logger.info("max_staff_alert_retired conv_id=%s edited=%s", conversation_id, edited)
    return edited
