"""DRF serializer for public Lead creation (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead + сериализатор;
docs/security-baseline.md §3 (validate; whitelist; honeypot silent drop).

Контракт:
- Публичный POST создаёт Lead (Slice 19 — endpoint + throttle + honeypot).
- Whitelist полей (no mass assignment): только клиентские поля доступны
  для записи; status/created_at/updated_at — read-only.
- Валидация: email format, message длина (anti-spam + DoS guard),
  lead_type из choices.
- PII-safe response: email/phone — write-only (не возвращаются в ответе).
- Honeypot: поле `website` (hidden в UI); если заполнено — silent drop
  в view (заявка не создаётся, но возвращается 201).
"""

from __future__ import annotations

from rest_framework import serializers

from leads.models import Lead

# Message length bounds (anti-spam + DoS guard).
_MESSAGE_MIN_LENGTH = 10
_MESSAGE_MAX_LENGTH = 5000


class LeadSerializer(serializers.ModelSerializer):
    """Serializer for public Lead creation (RFQ / consultation / replacement).

    Only client-facing fields are writable; status/timestamps are read-only.
    `email` and `phone` are write-only (PII-safe response). `website` is a
    honeypot field — the view silently drops submissions where it's filled.
    """

    # Honeypot: hidden field in UI; bots fill it, real users never see it.
    website = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="Honeypot — leave empty (hidden from real users).",
    )

    class Meta:
        model = Lead
        fields = (
            "id",
            "lead_type",
            "name",
            "email",
            "phone",
            "company",
            "message",
            "sku",
            "quantity",
            "analog_belimo_code",
            "status",
            "created_at",
            "updated_at",
            "website",
        )
        read_only_fields = ("id", "status", "created_at", "updated_at")
        # PII-safe response: email/phone are write-only (never returned to client).
        extra_kwargs = {
            "email": {"write_only": True},
            "phone": {"write_only": True},
        }

    def validate_message(self, value: str) -> str:
        """Reject too-short (spam) and too-long (DoS) messages.

        Args:
            value: raw message text from the request.

        Returns:
            The validated message.

        Raises:
            ValidationError: if length is outside [_MESSAGE_MIN_LENGTH, _MESSAGE_MAX_LENGTH].
        """
        length = len(value)
        if length < _MESSAGE_MIN_LENGTH:
            raise serializers.ValidationError(
                f"Message must be at least {_MESSAGE_MIN_LENGTH} characters.",
            )
        if length > _MESSAGE_MAX_LENGTH:
            raise serializers.ValidationError(
                f"Message must be at most {_MESSAGE_MAX_LENGTH} characters.",
            )
        return value

    def create(self, validated_data: dict) -> Lead:
        """Create a Lead, stripping the honeypot field before ORM create.

        Args:
            validated_data: validated payload including the `website` honeypot.

        Returns:
            The created Lead instance (without the honeypot field).
        """
        # Pop honeypot — it's not a model field; the view checks it before save.
        validated_data.pop("website", None)
        return Lead.objects.create(**validated_data)
