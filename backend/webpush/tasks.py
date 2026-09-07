"""Celery tasks for Web Push delivery."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.webpush")


@shared_task
def notify_staff_support_inbound(conversation_id: int) -> int:
    """Push staff: new inbound support message (if enabled in SiteSettings)."""
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_support_push_copy
    from supportchat.models import Conversation
    from webpush.services import queryset_staff_alerts, send_push_to_subscription

    if not SiteSettings.load().staff_push_support_enabled:
        return 0
    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    label = conv.display_name or conv.get_channel_display()
    title, body = staff_support_push_copy(label=label)
    url = f"/admin/supportchat/conversation/{conv.pk}/change/"
    sent = 0
    for sub in queryset_staff_alerts().iterator():
        if send_push_to_subscription(
            sub,
            title=title,
            body=body,
            url=url,
            tag=f"support-{conv.pk}",
        ):
            sent += 1
    return sent


@shared_task
def notify_staff_new_lead(lead_id: int) -> int:
    """Push staff Admin PWA: new lead (if enabled in SiteSettings)."""
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_lead_push_copy
    from webpush.services import queryset_staff_alerts, send_push_to_subscription

    if not SiteSettings.load().staff_push_leads_enabled:
        return 0
    try:
        lead = Lead.objects.get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title, body = staff_lead_push_copy(
        name=lead.name,
        lead_type=lead.get_lead_type_display(),
    )
    url = f"/admin/leads/lead/{lead.pk}/change/"
    sent = 0
    for sub in queryset_staff_alerts().iterator():
        if send_push_to_subscription(
            sub,
            title=title,
            body=body,
            url=url,
            tag=f"lead-{lead.pk}",
        ):
            sent += 1
    return sent


@shared_task
def notify_visitor_support_reply(conversation_id: int) -> int:
    """Push visitor: staff replied on web chat."""
    from supportchat.models import Channel, Conversation
    from webpush.services import queryset_session_support, send_push_to_subscription

    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if conv.channel != Channel.WEB:
        return 0
    session_key = conv.external_user_id
    title = "Ответ поддержки Hoocon"
    body = "Менеджер ответил в чате на сайте"
    url = "/?chat=1"
    sent = 0
    for sub in queryset_session_support(session_key).iterator():
        if send_push_to_subscription(sub, title=title, body=body, url=url, tag=f"support-reply-{conv.pk}"):
            sent += 1
    return sent


@shared_task
def broadcast_marketing_push(
    *,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "marketing",
) -> int:
    """Send marketing/news push to all marketing subscribers."""
    from webpush.services import queryset_marketing, send_push_to_subscription

    sent = 0
    for sub in queryset_marketing().iterator():
        if send_push_to_subscription(sub, title=title, body=body, url=url, tag=tag):
            sent += 1
    logger.info("webpush_broadcast_sent=%s", sent)
    return sent


@shared_task
def deliver_web_push_ids(
    subscription_ids: list[int],
    title: str,
    body: str,
    url: str = "/",
    tag: str = "hoocon",
) -> int:
    """Low-level: deliver to explicit subscription pks."""
    from webpush.models import PushSubscription
    from webpush.services import send_push_to_subscription

    sent = 0
    for sub in PushSubscription.objects.filter(pk__in=subscription_ids).iterator():
        if send_push_to_subscription(sub, title=title, body=body, url=url, tag=tag):
            sent += 1
    return sent
