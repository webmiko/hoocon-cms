"""DRF serializer for public Lead creation (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead + сериализатор;
docs/security-baseline.md §3 (validate; whitelist; honeypot silent drop).

Контракт:
- Публичный POST создаёт Lead (Slice 19 — endpoint + throttle + honeypot).
- Whitelist полей (no mass assignment): только клиентские поля доступны
  для записи; status/created_at/updated_at — read-only.
- RFQ: ``company`` обязательна; ``items`` — позиции SKU (или legacy ``sku``).
- Валидация: email format, message длина (anti-spam + DoS guard),
  lead_type из choices.
- PII-safe response: email/phone — write-only (не возвращаются в ответе).
- Honeypot: поле `website` (hidden в UI); если заполнено — silent drop
  в view (заявка не создаётся, но возвращается 201).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from catalog.models import SKU
from leads.models import Lead, LeadItem
from leads.rfq_bundle import attach_rfq_bundle

# Message length bounds (anti-spam + DoS guard).
_MESSAGE_MIN_LENGTH = 10
_MESSAGE_MAX_LENGTH = 5000
_MAX_LEAD_ITEMS = 30


class LeadItemWriteSerializer(serializers.Serializer):
    """One RFQ line: published SKU slug and/or free-text sku_code."""

    sku = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=SKU.objects.filter(is_published=True),
        required=False,
        allow_null=True,
    )
    sku_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
        default="",
    )
    quantity = serializers.IntegerField(min_value=1, default=1, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Require sku FK or non-empty sku_code."""
        sku = attrs.get("sku")
        code = (attrs.get("sku_code") or "").strip()
        if sku is None and not code:
            raise serializers.ValidationError(
                "Укажите sku (slug) или sku_code.",
            )
        if sku is not None and not code:
            attrs["sku_code"] = sku.sku_code
        else:
            attrs["sku_code"] = code
        attrs["quantity"] = attrs.get("quantity") or 1
        return attrs


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
    sku = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=SKU.objects.filter(is_published=True),
        required=False,
        allow_null=True,
    )
    items = LeadItemWriteSerializer(many=True, required=False, write_only=True)

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
            "items",
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
        """Reject too-short (spam) and too-long (DoS) messages."""
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

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cap line count."""
        if len(value) > _MAX_LEAD_ITEMS:
            raise serializers.ValidationError(
                f"Не больше {_MAX_LEAD_ITEMS} позиций в одной заявке.",
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """RFQ requires company; normalize items vs legacy sku."""
        lead_type = attrs.get("lead_type", Lead.LeadType.RFQ)
        company = (attrs.get("company") or "").strip()
        attrs["company"] = company
        if lead_type == Lead.LeadType.RFQ and not company:
            raise serializers.ValidationError(
                {"company": "Для запроса КП укажите компанию."},
            )

        items = attrs.get("items")
        legacy_sku = attrs.get("sku")
        legacy_qty = attrs.get("quantity")
        if items is None:
            items = []
        if not items and legacy_sku is not None:
            items = [
                {
                    "sku": legacy_sku,
                    "sku_code": legacy_sku.sku_code,
                    "quantity": legacy_qty or 1,
                },
            ]
        attrs["_resolved_items"] = items

        if items:
            first = items[0]
            attrs["sku"] = first.get("sku")
            attrs["quantity"] = first.get("quantity") or 1
        return attrs

    def create(self, validated_data: dict) -> Lead:
        """Create Lead + LeadItem rows, then attach RFQ soft-bundle."""
        validated_data.pop("website", None)
        items_data: list[dict[str, Any]] = validated_data.pop("_resolved_items", [])
        validated_data.pop("items", None)

        lead = Lead.objects.create(**validated_data)
        for index, row in enumerate(items_data):
            sku = row.get("sku")
            LeadItem.objects.create(
                lead=lead,
                sku=sku,
                sku_code=(row.get("sku_code") or "").strip() or (sku.sku_code if sku is not None else ""),
                quantity=row.get("quantity") or 1,
                sort_order=index,
            )
        attach_rfq_bundle(lead)
        lead.refresh_from_db()
        return lead
