"""FCM push tasks for the manager Flutter app."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def _fcm_server_key() -> str:
    return str(getattr(settings, "FCM_SERVER_KEY", "") or "").strip()


def _send_fcm(*, token: str, title: str, body: str, data: dict[str, str]) -> bool:
    """Legacy FCM HTTP API (server key). No-op if key unset."""
    key = _fcm_server_key()
    if not key:
        logger.debug("FCM_SERVER_KEY unset — skip push")
        return False
    payload = {
        "to": token,
        "notification": {"title": title, "body": body},
        "data": data,
        "priority": "high",
    }
    req = urllib.request.Request(
        "https://fcm.googleapis.com/fcm/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"key={key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — fixed FCM URL
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("FCM HTTP error %s", exc.code)
        return False
    except Exception:  # noqa: BLE001
        logger.exception("FCM send failed")
        return False


@shared_task
def notify_staff_fcm_support(conversation_id: int) -> int:
    """FCM: new inbound support message."""
    from staff_api.models import StaffDevice
    from supportchat.models import Conversation
    from supportchat.services import conversation_party_label

    try:
        conv = Conversation.objects.select_related("client", "lead").get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0
    title = "Новое сообщение в поддержке"
    label = conversation_party_label(conv)
    body = f"{label}: новое обращение"
    data = {
        "type": "support",
        "conversation_id": str(conv.pk),
        "deep_link": f"hoocon-manager://conversation/{conv.pk}",
    }
    sent = 0
    for device in StaffDevice.objects.select_related("user").filter(user__is_active=True, user__is_staff=True):
        if _send_fcm(token=device.fcm_token, title=title, body=body, data=data):
            sent += 1
    return sent


@shared_task
def notify_staff_fcm_new_lead(lead_id: int) -> int:
    """FCM: new lead created."""
    from leads.models import Lead
    from staff_api.models import StaffDevice

    try:
        lead = Lead.objects.get(pk=lead_id)
    except Lead.DoesNotExist:
        return 0
    title = "Новая заявка"
    body = f"{lead.name}: {lead.get_lead_type_display()}"
    data = {
        "type": "lead",
        "lead_id": str(lead.pk),
        "deep_link": f"hoocon-manager://lead/{lead.pk}",
    }
    sent = 0
    for device in StaffDevice.objects.select_related("user").filter(user__is_active=True, user__is_staff=True):
        if _send_fcm(token=device.fcm_token, title=title, body=body, data=data):
            sent += 1
    return sent
