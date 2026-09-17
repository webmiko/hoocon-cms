"""DRF serializers for public support widget API."""

from __future__ import annotations

from rest_framework import serializers

from supportchat.models import Message
from supportchat.services import message_sender_name


class ConversationStartSerializer(serializers.Serializer):
    """Optional contact fields when starting / resuming a web chat."""

    display_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)


class MessageCreateSerializer(serializers.Serializer):
    """Client inbound message (+ honeypot)."""

    body = serializers.CharField(max_length=4000)
    chat_action = serializers.ChoiceField(
        choices=("call_manager", "continue_bot"),
        required=False,
        allow_blank=True,
    )
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)


class MessageSerializer(serializers.ModelSerializer):
    """Public message row (sender label only — no author email/username)."""

    sender_name = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "direction",
            "body",
            "outside_hours",
            "created_at",
            "sender_name",
            "actions",
        )
        read_only_fields = fields

    def get_sender_name(self, obj: Message) -> str:
        return message_sender_name(obj)

    def get_actions(self, obj: Message) -> list[dict[str, str]]:
        from supportchat.gigachat.chat_actions import normalize_chat_actions

        payload = obj.raw_payload if isinstance(obj.raw_payload, dict) else {}
        return normalize_chat_actions(payload.get("chat_actions"))
