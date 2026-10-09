"""Server-side consent to personal-data processing (152-ФЗ).

The browser checkbox is not proof: every form that sends a name, email or
phone must also send ``pdn_consent: true``; the server stamps when it was
given and which policy text (``PDN_POLICY_VERSION``) the visitor agreed to.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import serializers

PDN_CONSENT_REQUIRED = "Подтвердите согласие на обработку персональных данных."


class PdnConsentFields(models.Model):
    """When and under which policy version the person agreed to PDN processing."""

    pdn_consent_at = models.DateTimeField(
        "согласие на обработку ПДн",
        null=True,
        blank=True,
        editable=False,
        help_text="Когда человек отметил согласие в форме на сайте.",
    )
    pdn_policy_version = models.CharField(
        "версия политики ПДн",
        max_length=32,
        blank=True,
        default="",
        editable=False,
        help_text="Редакция политики конфиденциальности на момент согласия.",
    )

    class Meta:
        abstract = True


def stamp_pdn_consent(obj: PdnConsentFields) -> None:
    """Record consent now under the current policy version (caller saves)."""
    obj.pdn_consent_at = timezone.now()
    obj.pdn_policy_version = settings.PDN_POLICY_VERSION


def pdn_consent_field(*, required: bool = True) -> serializers.BooleanField:
    """Write-only flag; ``required`` forms reject anything but ``true``."""
    return serializers.BooleanField(
        write_only=True,
        required=required,
        default=False if not required else serializers.empty,
        error_messages={"required": PDN_CONSENT_REQUIRED, "invalid": PDN_CONSENT_REQUIRED},
    )


def require_pdn_consent(value: bool) -> bool:
    """Serializer ``validate_pdn_consent`` body."""
    if value is not True:
        raise serializers.ValidationError(PDN_CONSENT_REQUIRED)
    return value
