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
def notify_staff_telegram_support(
    conversation_id: int,
    inbound_message_id: int | None = None,
) -> int:
    """Telegram alert for inbound support — parallel channel (reply button lives here)."""
    from accounts.telegram_alerts import (
        format_staff_telegram_message,
        send_telegram_to_users,
        staff_telegram_recipients_managers,
        staff_telegram_recipients_superusers,
    )
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_support_push_copy
    from supportchat.models import Conversation
    from supportchat.services import claim_staff_support_push, inbound_superseded

    if inbound_message_id is not None and inbound_superseded(
        conversation_id,
        inbound_message_id,
    ):
        return 0
    site = SiteSettings.load()
    if not site.staff_telegram_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if not claim_staff_support_push("telegram", conv.pk, inbound_message_id):
        return 0
    label = conv.display_name or conv.get_channel_display()
    title, body = staff_support_push_copy(label=label)
    page = (conv.page_url or "").strip()
    if page:
        body = f"{body}\nСтраница: {page}"
    from supportchat.models import Message, MessageDirection

    inbound = None
    if inbound_message_id is not None:
        inbound = Message.objects.filter(
            pk=inbound_message_id,
            conversation_id=conv.pk,
            direction=MessageDirection.INBOUND,
        ).first()
    if inbound is None:
        inbound = (
            Message.objects.filter(
                conversation_id=conv.pk,
                direction=MessageDirection.INBOUND,
            )
            .order_by("-id")
            .first()
        )
    if inbound is not None and inbound.attachment:
        from django.conf import settings

        site_url = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
        name = inbound.attachment_name or "файл"
        body = f"{body}\n📎 {name}: {site_url}{inbound.attachment.url}"
    text = format_staff_telegram_message(
        title=title,
        body=body,
        url=f"/admin/supportchat/conversation/{conv.pk}/change/",
    )
    users = list(staff_telegram_recipients_managers()) + list(staff_telegram_recipients_superusers())
    from social.telegram_staff_reply import (
        staff_support_alert_reply_markup,
        store_support_alert_message_id,
    )

    mids: dict[str, str] = {}
    sent = send_telegram_to_users(
        users,
        text,
        reply_markup=staff_support_alert_reply_markup(conv.pk),
        mids_out=mids,
    )
    for chat_id, message_id in mids.items():
        store_support_alert_message_id(conv.pk, chat_id, message_id, text)
    logger.info("telegram_staff_support conv_id=%s sent=%s", conversation_id, sent)
    return sent


@shared_task
def retire_telegram_support_alert(conversation_id: int, author_user_id: int | None) -> int:
    """After a staff reply, remove «Ответить» and mark who answered."""
    from django.contrib.auth import get_user_model

    from accounts.telegram_alerts import (
        staff_telegram_recipients_managers,
        staff_telegram_recipients_superusers,
        telegram_chat_id_for,
    )
    from social.publishers import telegram_api_call
    from social.telegram_staff_reply import load_support_alert_message_id
    from supportchat.services import staff_public_name

    author = get_user_model().objects.filter(pk=author_user_id).first() if author_user_id else None
    author_label = staff_public_name(author)
    recipients = list(staff_telegram_recipients_managers()) + list(staff_telegram_recipients_superusers())
    edited = 0
    for user in recipients:
        chat_id = telegram_chat_id_for(user)
        if not chat_id:
            continue
        stored = load_support_alert_message_id(conversation_id, chat_id)
        if not stored:
            continue
        is_author = author is not None and user.pk == author.pk
        suffix = "\n\n✅ Вы ответили" if is_author else f"\n\n✅ Ответил: {author_label}"
        mid = stored["message_id"]
        result = telegram_api_call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": int(mid) if mid.isdigit() else mid,
                "text": stored["text"] + suffix,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            },
        )
        if result.ok:
            edited += 1
    logger.info(
        "telegram_staff_alert_retired conv_id=%s edited=%s",
        conversation_id,
        edited,
    )
    return edited


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


@shared_task
def send_ops_telegram_alert_task(title: str, body: str, dedup_key: str) -> int:
    """Ops channel alert (HTTP 5xx, monitor-health failures)."""
    from config.ops_alerts import send_ops_telegram_alert

    sent = send_ops_telegram_alert(title=title, body=body, dedup_key=dedup_key)
    logger.info("ops_telegram_alert dedup=%s sent=%s", dedup_key, sent)
    return sent
