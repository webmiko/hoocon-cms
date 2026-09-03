"""Serializers for public analytics hit API."""

from __future__ import annotations

from rest_framework import serializers

from analytics.models import ObjectType


class PageHitSerializer(serializers.Serializer):
    """POST body for ``/api/analytics/hit/``."""

    path = serializers.CharField(max_length=512)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    object_type = serializers.ChoiceField(
        choices=ObjectType.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    object_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
