"""Serializer for ProductFile upload (staff) and public read.

Spec: ПЛАН §6 Iter 2 — upload view + validation; docs/security-baseline.md §1.
"""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from catalog.docs_hub import public_pdf_url
from catalog.models import SKU, ProductFile
from catalog.validators import sanitize_upload_filename, validate_pdf_upload


class ProductFileUploadSerializer(serializers.ModelSerializer):
    """Serializer for staff upload (POST) and public read (GET)."""

    class Meta:
        model = ProductFile
        fields = ("id", "title", "file", "file_type", "is_published", "sort_order")
        read_only_fields = ("id",)

    def validate_file(self, value: UploadedFile) -> UploadedFile:
        """Run PDF validators (extension, MIME, magic, size) on upload.

        Args:
            value: uploaded file from the request.

        Returns:
            The same file after validation.

        Raises:
            ValidationError: on quarantine / validation failure.
        """
        try:
            validate_pdf_upload(value)
            name = getattr(value, "name", "") or ""
            if name:
                sanitize_upload_filename(name)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.messages if hasattr(exc, "messages") else str(exc),
            ) from exc
        return value

    def to_representation(self, instance: ProductFile) -> dict[str, object]:
        """Public read returns the stable document URL, not the storage path."""
        data = super().to_representation(instance)
        sku = cast(SKU, instance.sku)
        data["file"] = public_pdf_url(
            sku_code=sku.sku_code,
            title=instance.title,
            file_type=instance.file_type,
            request=self.context.get("request"),
        )
        return data
