"""Serializers for staff mobile API."""

from __future__ import annotations

from rest_framework import serializers

from crm.models import ActivityType, Client
from leads.models import Lead
from supportchat.models import Conversation, Message
from supportchat.services import (
    conversation_party_company,
    conversation_party_label,
    conversation_party_phone,
)


class OtpStartSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=254)


class OtpVerifySerializer(serializers.Serializer):
    challenge_id = serializers.CharField(max_length=128)
    code = serializers.CharField(max_length=16)


class OtpResendSerializer(serializers.Serializer):
    challenge_id = serializers.CharField(max_length=128)


class LeadStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            Lead.LeadStatus.IN_PROGRESS,
            Lead.LeadStatus.DONE,
        ],
    )


class ActivityCreateSerializer(serializers.Serializer):
    activity_type = serializers.ChoiceField(
        choices=ActivityType.choices,
        default=ActivityType.NOTE,
    )
    subject = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    body = serializers.CharField(max_length=10000, allow_blank=True, required=False, default="")


class EmailCreateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField(max_length=20000)
    to_email = serializers.EmailField(required=False, allow_blank=True, default="")
    send_now = serializers.BooleanField(default=True)


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)


class DeviceSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=["android", "ios"], default="android")


def serialize_user(user) -> dict:
    from accounts.roles import staff_sees_all_leads

    groups = list(user.groups.values_list("name", flat=True))
    return {
        "id": user.pk,
        "email": user.email or "",
        "username": user.get_username(),
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "display_name": (user.get_full_name() or user.email or user.get_username()),
        "groups": groups,
        "sees_all_leads": staff_sees_all_leads(user),
        "is_superuser": bool(user.is_superuser),
    }


def serialize_lead(lead: Lead, *, detail: bool = False) -> dict:
    data = {
        "id": lead.pk,
        "status": lead.status,
        "status_label": lead.get_status_display(),
        "name": getattr(lead, "name", "") or "",
        "email": getattr(lead, "email", "") or "",
        "phone": getattr(lead, "phone", "") or "",
        "company": getattr(lead, "company", "") or "",
        "source": getattr(lead, "source", "") or "",
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "seen_at": lead.seen_at.isoformat() if lead.seen_at else None,
        "assignee_id": lead.assignee_id,
        "client_id": lead.client_id,
    }
    if detail:
        data["message"] = getattr(lead, "message", "") or getattr(lead, "body", "") or ""
        data["comment"] = getattr(lead, "comment", "") or ""
    return data


def serialize_client(client: Client, *, detail: bool = False) -> dict:
    data = {
        "id": client.pk,
        "name": client.name or "",
        "email": client.email or "",
        "phone": client.phone or "",
        "company": client.company or "",
        "assignee_id": client.assignee_id,
        "is_active": client.is_active,
    }
    if detail:
        data["notes"] = client.notes or ""
        acts = list(
            client.activities.select_related("author").order_by("-created_at")[:20],
        )
        data["activities"] = [
            {
                "id": a.pk,
                "activity_type": a.activity_type,
                "subject": a.subject or "",
                "body": a.body or "",
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "author": (a.author.get_full_name() if a.author else "") or "",
            }
            for a in acts
        ]
        emails = list(client.emails.order_by("-created_at")[:10])
        data["emails"] = [
            {
                "id": e.pk,
                "subject": e.subject or "",
                "status": e.status,
                "direction": e.direction,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in emails
        ]
    return data


def serialize_conversation(conv: Conversation) -> dict:
    """Hub row: ``title`` / ``display_name`` = party label (name·company or phone)."""
    title = conversation_party_label(conv)
    return {
        "id": conv.pk,
        "channel": conv.channel,
        "channel_label": conv.get_channel_display(),
        "status": conv.status,
        "title": title,
        "display_name": title,
        "visitor_name": (conv.display_name or "").strip(),
        "contact_email": (conv.contact_email or "").strip(),
        "company": conversation_party_company(conv),
        "phone": conversation_party_phone(conv),
        "staff_unread_count": conv.staff_unread_count,
        "last_message_at": (conv.last_message_at.isoformat() if conv.last_message_at else None),
        "assignee_id": conv.assignee_id,
        "client_id": conv.client_id,
        "lead_id": conv.lead_id,
        # Mobile may delete only chats without a CRM client link.
        "deletable": conv.client_id is None,
    }


def serialize_message(msg: Message) -> dict:
    return {
        "id": msg.pk,
        "direction": msg.direction,
        "body": msg.body or "",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "outside_hours": bool(getattr(msg, "outside_hours", False)),
    }
