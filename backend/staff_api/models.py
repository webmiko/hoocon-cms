"""Models: auth tokens and FCM device registrations for staff mobile."""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_staff_token() -> str:
    """Return a new opaque API token (store as-is; treat like a password)."""
    return secrets.token_urlsafe(32)


class StaffAuthToken(models.Model):
    """Bearer token for ``/api/staff/`` (Flutter manager app)."""

    key = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_auth_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Токен staff API")
        verbose_name_plural = _("Токены staff API")

    def __str__(self) -> str:
        return f"StaffAuthToken(user={self.user_id})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.key:
            self.key = generate_staff_token()
        super().save(*args, **kwargs)


class StaffDevice(models.Model):
    """FCM registration for push to the manager app."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_devices",
    )
    fcm_token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(
        max_length=16,
        choices=Platform.choices,
        default=Platform.ANDROID,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Устройство менеджера")
        verbose_name_plural = _("Устройства менеджеров")

    def __str__(self) -> str:
        return f"StaffDevice({self.platform}, user={self.user_id})"
