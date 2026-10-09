"""DRF serializers for public support widget API."""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from config.pdn import pdn_consent_field
from supportchat.attachments import (
    DOWNLOAD_TYPES,
    FALLBACK_TYPE,
    claims_image_without_raster_bytes,
    normalize_mime,
)
from supportchat.models import Message
from supportchat.presentation import message_attachment_is_image, message_sender_name


class ConversationStartSerializer(serializers.Serializer):
    """Optional contact fields when starting / resuming a web chat."""

    display_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    page_url = serializers.RegexField(
        r"^/\S{0,498}$",
        required=False,
        allow_blank=True,
        max_length=500,
    )
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)
    # Required (true) whenever name/email are sent — checked with the thread state in the service.
    pdn_consent = pdn_consent_field(required=False)


_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
_ATTACHMENT_MIME_TYPES = DOWNLOAD_TYPES | {FALLBACK_TYPE}


class MessageCreateSerializer(serializers.Serializer):
    """Client inbound message (+ honeypot, optional file)."""

    body = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    attachment = serializers.FileField(required=False)
    chat_action = serializers.RegexField(
        r"^(call_manager|continue_bot|quiz:[a-z0-9_:]{1,60})$",
        required=False,
        allow_blank=True,
        max_length=80,
    )
    page_url = serializers.RegexField(
        r"^/\S{0,498}$",
        required=False,
        allow_blank=True,
        max_length=500,
    )
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate_attachment(self, file: UploadedFile | None) -> UploadedFile | None:
        """Size + mime allowlist for widget uploads."""
        if file is None:
            return file
        if (file.size or 0) > _ATTACHMENT_MAX_BYTES:
            raise serializers.ValidationError("Файл больше 10 МБ.")
        claimed = getattr(file, "content_type", "") or ""
        mime = normalize_mime(claimed)
        if mime.startswith("image/"):
            if claims_image_without_raster_bytes(file, claimed):
                raise serializers.ValidationError("Картинка — только JPG, PNG, WebP или GIF.")
            return file
        if mime not in _ATTACHMENT_MIME_TYPES:
            raise serializers.ValidationError("Этот тип файла не поддерживается.")
        return file

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Either a non-empty body or an attachment is required."""
        body = (attrs.get("body") or "").strip()
        if not body and attrs.get("attachment") is None:
            raise serializers.ValidationError({"body": "Введите сообщение."})
        return attrs


class MessageSerializer(serializers.ModelSerializer):
    """Public message row (sender label only — no author email/username)."""

    sender_name = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()
    attachment_name = serializers.SerializerMethodField()
    attachment_is_image = serializers.SerializerMethodField()

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
            "attachment_url",
            "attachment_name",
            "attachment_is_image",
        )
        read_only_fields = fields

    def get_sender_name(self, obj: Message) -> str:
        return message_sender_name(obj)

    def get_attachment_url(self, obj: Message) -> str:
        from supportchat.attachments import message_attachment_url

        path = message_attachment_url(obj)
        request = self.context.get("request")
        if path and request is not None:
            return request.build_absolute_uri(path)
        return path

    def get_attachment_name(self, obj: Message) -> str:
        return obj.attachment_name

    def get_attachment_is_image(self, obj: Message) -> bool:
        return bool(obj.attachment) and message_attachment_is_image(obj)

    def get_actions(self, obj: Message) -> list[dict[str, str]]:
        from supportchat.gigachat.chat_actions import normalize_chat_actions

        payload = obj.raw_payload if isinstance(obj.raw_payload, dict) else {}
        return normalize_chat_actions(payload.get("chat_actions"))
