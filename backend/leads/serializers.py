"""DRF serializer for public Lead creation (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead + сериализатор;
docs/security-baseline.md §3 (validate; whitelist; honeypot в Slice 19).

Контракт:
- Публичный POST создаёт Lead (Slice 19 — endpoint + throttle + honeypot).
- Whitelist полей (no mass assignment): только клиентские поля доступны
  для записи; status/created_at/updated_at — read-only.
- Валидация: email format, message длина (anti-spam + DoS guard),
  lead_type из choices.
- PII: name/email/phone — контактные; Slice 19 контролирует экспозицию
  в публичном ответе (по умолчанию не возвращаем email/phone в ответе).
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
    Honeypot field and throttle are enforced in the view (Slice 19).
    """

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
        )
        read_only_fields = ("id", "status", "created_at", "updated_at")

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
