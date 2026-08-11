"""PushSubscription model for Web Push (VAPID)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PushSubscription(models.Model):
    """One browser/PWA push endpoint with topic flags."""

    endpoint: models.URLField = models.URLField(
        "endpoint",
        max_length=2048,
        unique=True,
    )
    p256dh: models.CharField = models.CharField("p256dh", max_length=200)
    auth: models.CharField = models.CharField("auth", max_length=100)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="push_subscriptions",
        verbose_name="пользователь",
    )
    session_key: models.CharField = models.CharField(
        "session key",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Django session key for anonymous support-chat visitors.",
    )
    topic_support: models.BooleanField = models.BooleanField(
        "чат поддержки",
        default=False,
    )
    topic_marketing: models.BooleanField = models.BooleanField(
        "маркетинг / новости",
        default=False,
    )
    created_at = models.DateTimeField("создана", auto_now_add=True)
    last_seen_at = models.DateTimeField("последняя активность", auto_now=True)

    class Meta:
        verbose_name = "push-подписка"
        verbose_name_plural = "push-подписки"
        ordering = ("-last_seen_at",)

    def __str__(self) -> str:
        topics = []
        if self.topic_support:
            topics.append("support")
        if self.topic_marketing:
            topics.append("marketing")
        return f"{self.endpoint[:48]}… [{','.join(topics) or 'none'}]"

    def touch(self) -> None:
        """Bump last_seen_at without changing other fields."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])
