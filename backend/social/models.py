"""Models for social network announcement log."""

from __future__ import annotations

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class SocialChannel(models.TextChoices):
    """Supported outbound channels."""

    TELEGRAM = "telegram", "Telegram"
    VK = "vk", "VK"
    MAX = "max", "MAX"


class SocialPostStatus(models.TextChoices):
    """Delivery status of one channel post."""

    PENDING = "pending", "В очереди"
    SENT = "sent", "Отправлено"
    FAILED = "failed", "Ошибка"
    SKIPPED = "skipped", "Пропущено"


class SocialPost(models.Model):
    """One announcement attempt for a content object on one channel.

    Used for Admin history and idempotency (do not re-send SENT without force).
    """

    content_type: models.ForeignKey = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="тип контента",
    )
    object_id: models.PositiveIntegerField = models.PositiveIntegerField("ID объекта")
    content_object = GenericForeignKey("content_type", "object_id")
    channel: models.CharField = models.CharField(
        "канал",
        max_length=20,
        choices=SocialChannel.choices,
        db_index=True,
    )
    status: models.CharField = models.CharField(
        "статус",
        max_length=20,
        choices=SocialPostStatus.choices,
        default=SocialPostStatus.PENDING,
        db_index=True,
    )
    message_preview: models.TextField = models.TextField(
        "текст анонса",
        blank=True,
        default="",
    )
    external_id: models.CharField = models.CharField(
        "ID во внешней системе",
        max_length=100,
        blank=True,
        default="",
    )
    error_message: models.TextField = models.TextField(
        "ошибка",
        blank=True,
        default="",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    sent_at: models.DateTimeField | None = models.DateTimeField(
        "отправлено",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "анонс в соцсеть"
        verbose_name_plural = "анонсы в соцсети"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("content_type", "object_id", "channel")),
        ]

    def __str__(self) -> str:
        """Return channel + status for Admin lists."""
        return f"{self.get_channel_display()} — {self.get_status_display()}"

    @classmethod
    def content_type_for(cls, obj: models.Model) -> ContentType:
        """Resolve ContentType for a content instance.

        Args:
            obj: Article or News (or any model).

        Returns:
            ContentType for ``obj``.
        """
        return ContentType.objects.get_for_model(obj, for_concrete_model=False)

    def mark_sent(self, *, external_id: str = "") -> None:
        """Mark this post as successfully delivered."""
        self.status = SocialPostStatus.SENT
        self.external_id = external_id
        self.error_message = ""
        self.sent_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "external_id",
                "error_message",
                "sent_at",
            ]
        )

    def mark_failed(self, error: str) -> None:
        """Mark this post as failed with a safe error message."""
        self.status = SocialPostStatus.FAILED
        self.error_message = error[:2000]
        self.save(update_fields=["status", "error_message"])

    def mark_skipped(self, reason: str) -> None:
        """Mark as skipped (missing token/config)."""
        self.status = SocialPostStatus.SKIPPED
        self.error_message = reason[:2000]
        self.save(update_fields=["status", "error_message"])
