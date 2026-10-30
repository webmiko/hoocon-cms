"""Celery tasks: VK DMs to staff (managers + superusers)."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.vk_staff")


@shared_task
def notify_staff_vk_new_lead(lead_id: int) -> int:
    from accounts.telegram_alerts import without_staff_webpush
    from accounts.vk_alerts import (
        format_staff_vk_message,
        send_vk_to_users,
        staff_vk_recipients_managers,
        staff_vk_recipients_superusers,
    )
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_lead_push_copy

    site = SiteSettings.load()
    if not site.staff_vk_leads_enabled:
        return 0
    try:
        lead = Lead.objects.select_related("assignee").get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title, body = staff_lead_push_copy(
        name=lead.name,
        lead_type=lead.get_lead_type_display(),
    )
    text = format_staff_vk_message(
        title=title,
        body=body,
        url=f"/admin/leads/lead/{lead.pk}/change/",
    )
    managers = staff_vk_recipients_managers(lead_assignee_id=lead.assignee_id)
    users = without_staff_webpush(
        list(managers) + list(staff_vk_recipients_superusers()),
    )
    sent = send_vk_to_users(users, text)
    logger.info("vk_staff_lead lead_id=%s sent=%s", lead_id, sent)
    return sent


@shared_task
def notify_staff_vk_support(conversation_id: int, inbound_message_id: int | None = None) -> int:
    from accounts.vk_alerts import (
        format_staff_vk_message,
        send_vk_to_users,
        staff_vk_recipients_managers,
        staff_vk_recipients_superusers,
    )
    from sitesettings.models import SiteSettings
    from social.max_staff_reply import staff_reply_hint
    from social.vk_staff_reply import (
        staff_support_alert_keyboard,
        store_support_alert_mid,
    )
    from supportchat.models import Conversation
    from supportchat.services import (
        claim_staff_support_push,
        compose_staff_support_alert,
        inbound_superseded,
    )

    if inbound_message_id is not None and inbound_superseded(conversation_id, inbound_message_id):
        return 0
    site = SiteSettings.load()
    if not site.staff_vk_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if not claim_staff_support_push("vk", conv.pk, inbound_message_id):
        return 0
    title, body = compose_staff_support_alert(
        conv,
        inbound_message_id=inbound_message_id,
        reply_hint=staff_reply_hint(conv.pk),
    )
    text = format_staff_vk_message(
        title=title,
        body=body,
        url=f"/admin/supportchat/conversation/{conv.pk}/change/",
    )
    keyboard = staff_support_alert_keyboard(conv.pk)
    users = list(staff_vk_recipients_managers()) + list(staff_vk_recipients_superusers())
    cmids: dict[str, str] = {}
    sent = send_vk_to_users(users, text, keyboard=keyboard, cmids_out=cmids)
    for uid, cmid in cmids.items():
        store_support_alert_mid(conv.pk, uid, cmid, text)
    logger.info("vk_staff_support conv_id=%s sent=%s", conversation_id, sent)
    return sent


@shared_task
def retire_vk_support_alert(conversation_id: int, author_user_id: int | None = None) -> int:
    from accounts.vk_alerts import (
        staff_vk_recipients_managers,
        staff_vk_recipients_superusers,
        vk_user_id_for,
    )
    from social.publishers import edit_vk_message
    from social.vk_staff_reply import load_support_alert_mid
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
    author_label = staff_public_name(author)
    edited = 0
    empty_kb = '{"inline":true,"buttons":[]}'
    for user in list(staff_vk_recipients_managers()) + list(staff_vk_recipients_superusers()):
        uid = vk_user_id_for(user)
        if not uid:
            continue
        stored = load_support_alert_mid(conversation_id, uid)
        if not stored:
            continue
        is_author = author is not None and user.pk == author.pk
        suffix = "\n\n✅ Вы ответили" if is_author else f"\n\n✅ Ответил: {author_label}"
        result = edit_vk_message(
            peer_id=uid,
            conversation_message_id=str(stored["cmid"]),
            message=stored["text"] + suffix,
            keyboard=empty_kb,
        )
        if result.ok:
            edited += 1
    logger.info("vk_staff_alert_retired conv_id=%s edited=%s", conversation_id, edited)
    return edited


@shared_task
def notify_superuser_vk_crm(title: str, body: str, url: str = "") -> int:
    from accounts.telegram_alerts import without_staff_webpush
    from accounts.vk_alerts import (
        format_staff_vk_message,
        send_vk_to_users,
        staff_vk_recipients_superusers,
    )
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    if not site.staff_vk_superuser_crm_enabled:
        return 0
    text = format_staff_vk_message(title=title, body=body, url=url)
    users = without_staff_webpush(staff_vk_recipients_superusers())
    sent = send_vk_to_users(users, text)
    logger.info("vk_staff_crm sent=%s", sent)
    return sent
