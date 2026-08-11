"""Celery tasks for Web Push delivery."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.webpush")


@shared_task
def notify_staff_support_inbound(conversation_id: int) -> int:
    """Push staff: new inbound support message."""
    from supportchat.models import Conversation
    from webpush.services import queryset_staff_support, send_push_to_subscription

    try:
        conv = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    title = "Новое сообщение в поддержке"
    label = conv.display_name or conv.get_channel_display()
    body = f"{label}: новое обращение"
    url = f"/admin/supportchat/conversation/{conv.pk}/change/"
    sent = 0
    for sub in queryset_staff_support().iterator():
        if send_push_to_subscription(sub, title=title, body=body, url=url, tag=f"support-{conv.pk}"):
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
    url = "/"
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
