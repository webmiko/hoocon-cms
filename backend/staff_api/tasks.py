"""FCM push tasks for the manager Flutter app."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _send_fcm(*, token: str, title: str, body: str, data: dict[str, str]) -> bool:
    """FCM HTTP v1; forgets devices whose registration token is gone."""
    from staff_api.fcm import SendResult, send_fcm_message
    from staff_api.models import StaffDevice

    result = send_fcm_message(token=token, title=title, body=body, data=data)
    if result is SendResult.INVALID_TOKEN:
        StaffDevice.objects.filter(fcm_token=token).delete()
        logger.info("fcm_device_unregistered")
    return result is SendResult.SENT


def _push_to_staff_devices(*, title: str, body: str, data: dict[str, str]) -> int:
    from staff_api.models import StaffDevice

    tokens = list(
        StaffDevice.objects.filter(user__is_active=True, user__is_staff=True).values_list("fcm_token", flat=True),
    )
    return sum(1 for token in tokens if _send_fcm(token=token, title=title, body=body, data=data))


@shared_task
def notify_staff_fcm_support(
    conversation_id: int,
    inbound_message_id: int | None = None,
) -> int:
    """FCM: new inbound support message (if enabled in SiteSettings)."""
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_support_push_copy
    from supportchat.models import Conversation
    from supportchat.presentation import conversation_party_label
    from supportchat.services import claim_staff_support_push, inbound_superseded

    if inbound_message_id is not None and inbound_superseded(
        conversation_id,
        inbound_message_id,
    ):
        return 0
    if not SiteSettings.load().staff_push_support_enabled:
        return 0
    try:
        conv = Conversation.objects.select_related("client", "lead").get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    if not claim_staff_support_push("fcm", conv.pk, inbound_message_id):
        return 0
    title, body = staff_support_push_copy(label=conversation_party_label(conv))
    page = (conv.page_url or "").strip()
    if page:
        body = f"{body} · {page}"
    data = {
        "type": "support",
        "conversation_id": str(conv.pk),
        "deep_link": f"hoocon-manager://conversation/{conv.pk}",
    }
    return _push_to_staff_devices(title=title, body=body, data=data)


@shared_task
def notify_staff_fcm_new_lead(lead_id: int) -> int:
    """FCM: new lead created (if enabled in SiteSettings)."""
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from sitesettings.staff_push import staff_lead_push_copy

    if not SiteSettings.load().staff_push_leads_enabled:
        return 0
    try:
        lead = Lead.objects.get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title, body = staff_lead_push_copy(name=lead.name, lead_type=lead.get_lead_type_display())
    data = {
        "type": "lead",
        "lead_id": str(lead.pk),
        "deep_link": f"hoocon-manager://lead/{lead.pk}",
    }
    return _push_to_staff_devices(title=title, body=body, data=data)
