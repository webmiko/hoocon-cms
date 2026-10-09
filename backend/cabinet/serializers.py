"""Serializers for the client cabinet API (``/api/auth/*``, ``/api/account/*``).

PII policy: client-facing payloads never expose staff internals (assignee
names only as display label, no internal notes).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from cabinet.models import Order, OrderItem, RmaCase, SpecList, SpecListItem
from catalog.models import SKU
from config.pdn import pdn_consent_field, require_pdn_consent
from crm.models import ClientDocument, Quote
from leads.serializers import MAX_ITEM_QUANTITY


class RegisterSerializer(serializers.Serializer):
    """POST /api/auth/register/ payload (mode A)."""

    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=200, write_only=True)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    # Honeypot trap — bots fill it, humans never see it (silent reject).
    website = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    form_start_ts = serializers.FloatField(required=False, default=0)
    pdn_consent = pdn_consent_field()

    def validate_pdn_consent(self, value: bool) -> bool:
        return require_pdn_consent(value)


class LoginSerializer(serializers.Serializer):
    """POST /api/auth/login/ payload (mode A)."""

    email = serializers.EmailField()
    password = serializers.CharField(max_length=200, write_only=True)


class OtpStartSerializer(serializers.Serializer):
    """POST /api/auth/otp/start/ payload (mode B)."""

    email = serializers.EmailField()
    website = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    form_start_ts = serializers.FloatField(required=False, default=0)
    pdn_consent = pdn_consent_field()

    def validate_pdn_consent(self, value: bool) -> bool:
        return require_pdn_consent(value)


class OtpVerifySerializer(serializers.Serializer):
    """POST /api/auth/otp/verify/ payload."""

    challenge_id = serializers.CharField(max_length=200)
    code = serializers.CharField(min_length=4, max_length=10)


class OtpResendSerializer(serializers.Serializer):
    """POST /api/auth/otp/resend/ payload."""

    challenge_id = serializers.CharField(max_length=200)


class ProfilePatchSerializer(serializers.Serializer):
    """PATCH /api/account/me/ — editable profile fields only."""

    name = serializers.CharField(max_length=200, required=False)
    phone = serializers.CharField(max_length=50, required=False)


class SpecListItemSerializer(serializers.ModelSerializer):
    """One position inside a spec template."""

    class Meta:
        model = SpecListItem
        fields = ("id", "sku_code", "sku", "quantity", "position")
        read_only_fields = ("id",)


class SpecListSerializer(serializers.ModelSerializer):
    """SpecList with nested items (read); write via dedicated endpoints."""

    items = SpecListItemSerializer(many=True, read_only=True)

    class Meta:
        model = SpecList
        fields = ("id", "name", "note", "items", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


SPEC_MAX_ITEMS = 300


class SpecListItemWriteSerializer(serializers.Serializer):
    """Client-submitted position: published SKU by id, or a free-text code."""

    sku = serializers.PrimaryKeyRelatedField(
        queryset=SKU.objects.filter(is_published=True),
        required=False,
        allow_null=True,
    )
    sku_code = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_ITEM_QUANTITY, required=False, default=1)
    position = serializers.IntegerField(min_value=0, max_value=10_000, required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("sku") is None and not attrs.get("sku_code", "").strip():
            raise serializers.ValidationError("Укажите артикул.")
        return attrs


class SpecListWriteSerializer(serializers.Serializer):
    """Create/update a spec: name + flat items list (replaces items)."""

    name = serializers.CharField(max_length=200)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    items: serializers.ListSerializer = serializers.ListSerializer(
        child=SpecListItemWriteSerializer(),
        required=False,
        default=list,
        max_length=SPEC_MAX_ITEMS,
    )


class QuoteSerializer(serializers.ModelSerializer):
    """Client-visible quote (no staff internals; total only when priced)."""

    status_label = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = (
            "id",
            "number",
            "status",
            "status_label",
            "comment",
            "total_amount",
            "sent_at",
            "created_at",
        )

    def get_status_label(self, obj: Quote) -> str:
        return obj.get_status_display()

    def get_total_amount(self, obj: Quote) -> str | None:
        """Total is shown only when the pricing flag allows it (§12.1)."""
        if not _client_sees_prices():
            return None
        total = sum((it.unit_price or 0) * it.quantity for it in obj.items.all())
        return str(total) if total else None


class DocumentSerializer(serializers.ModelSerializer):
    """Client-visible document row."""

    kind_label = serializers.SerializerMethodField()
    edo_status_label = serializers.SerializerMethodField()

    class Meta:
        model = ClientDocument
        fields = (
            "id",
            "title",
            "kind",
            "kind_label",
            "edo_status",
            "edo_status_label",
            "quote",
            "order",
            "created_at",
        )

    def get_kind_label(self, obj: ClientDocument) -> str:
        return obj.get_kind_display()

    def get_edo_status_label(self, obj: ClientDocument) -> str:
        return obj.get_edo_status_display() or ""


class OrderItemSerializer(serializers.ModelSerializer):
    """Order position — no unit price for clients (§12.1)."""

    class Meta:
        model = OrderItem
        fields = ("id", "sku_code", "sku", "quantity")


class OrderSerializer(serializers.ModelSerializer):
    """Client-visible order with progress and shipment tracking (ЛК-6/13)."""

    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.SerializerMethodField()
    carrier_label = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "status",
            "status_label",
            "progress",
            "planned_ship_date",
            "carrier",
            "carrier_label",
            "track_number",
            "items",
            "created_at",
        )

    def get_status_label(self, obj: Order) -> str:
        return obj.get_status_display()

    def get_carrier_label(self, obj: Order) -> str:
        return obj.get_carrier_display() or ""


class RmaCaseCreateSerializer(serializers.ModelSerializer):
    """POST /api/account/rma/ — client submits a reclamation (+фото, ЛК-12)."""

    class Meta:
        model = RmaCase
        fields = ("order", "serial_number", "subject", "description", "photo")

    def validate_order(self, order: Order | None) -> Order | None:
        """Owner-scope: RMA order must belong to the requester."""
        client = self.context.get("client")
        if order is not None and client is not None and order.client_id != client.pk:
            raise serializers.ValidationError("Заказ не найден.")
        return order


class RmaCaseSerializer(serializers.ModelSerializer):
    """Client-visible RMA row."""

    status_label = serializers.SerializerMethodField()
    has_photo = serializers.SerializerMethodField()

    class Meta:
        model = RmaCase
        fields = (
            "id",
            "subject",
            "description",
            "serial_number",
            "order",
            "status",
            "status_label",
            "has_photo",
            "created_at",
        )

    def get_status_label(self, obj: RmaCase) -> str:
        return obj.get_status_display()

    def get_has_photo(self, obj: RmaCase) -> bool:
        return bool(obj.photo)


def _client_sees_prices() -> bool:
    """Price visibility flag for cabinet totals (default off — §12.1)."""
    from django.conf import settings

    return bool(getattr(settings, "CABINET_SHOW_PRICES", False))
