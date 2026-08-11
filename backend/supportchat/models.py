"""Support chat models: conversations, messages, working schedule.

Spec: docs/plan-support-chat-social.md.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class Channel(models.TextChoices):
    """Inbound channel for a conversation."""

    WEB = "web", "Сайт"
    TELEGRAM = "telegram", "Telegram"
    VK = "vk", "VK"
    MAX = "max", "MAX"


class ConversationStatus(models.TextChoices):
    """Lifecycle of a support thread."""

    OPEN = "open", "Открыт"
    CLOSED = "closed", "Закрыт"


class MessageDirection(models.TextChoices):
    """Who authored the message."""

    INBOUND = "inbound", "Клиент"
    OUTBOUND = "outbound", "Менеджер"
    SYSTEM = "system", "Система"


class Conversation(models.Model):
    """One support thread (web session or messenger user)."""

    channel: models.CharField = models.CharField(
        "канал",
        max_length=16,
        choices=Channel.choices,
        db_index=True,
    )
    external_user_id: models.CharField = models.CharField(
        "внешний id / session",
        max_length=128,
        db_index=True,
        help_text="Telegram chat id, VK user id, или web support_session_id.",
    )
    display_name: models.CharField = models.CharField(
        "имя",
        max_length=200,
        blank=True,
        default="",
    )
    contact_email: models.EmailField = models.EmailField(
        "email",
        blank=True,
        default="",
    )
    status: models.CharField = models.CharField(
        "статус",
        max_length=16,
        choices=ConversationStatus.choices,
        default=ConversationStatus.OPEN,
        db_index=True,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
        verbose_name="ответственный",
    )
    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
        verbose_name="клиент CRM",
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
        verbose_name="заявка",
    )
    last_message_at = models.DateTimeField(
        "последнее сообщение",
        null=True,
        blank=True,
        db_index=True,
    )
    staff_unread_count: models.PositiveIntegerField = models.PositiveIntegerField(
        "непрочитано (staff)",
        default=0,
    )
    created_at = models.DateTimeField("создан", auto_now_add=True)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        verbose_name = "диалог"
        verbose_name_plural = "диалоги"
        ordering = ("-last_message_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("channel", "external_user_id"),
                name="supportchat_conversation_channel_external_uniq",
            ),
        ]

    def __str__(self) -> str:
        label = self.display_name or self.external_user_id
        return f"{self.get_channel_display()} · {label}"


class Message(models.Model):
    """Single message in a support conversation."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="диалог",
    )
    direction: models.CharField = models.CharField(
        "направление",
        max_length=16,
        choices=MessageDirection.choices,
        db_index=True,
    )
    body: models.TextField = models.TextField("текст")
    external_message_id: models.CharField = models.CharField(
        "id во внешнем канале",
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        help_text="Идемпотентность webhook (Telegram message_id и т.п.).",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_messages",
        verbose_name="автор (staff)",
    )
    outside_hours: models.BooleanField = models.BooleanField(
        "вне рабочих часов",
        default=False,
    )
    raw_payload = models.JSONField(
        "сырой payload",
        null=True,
        blank=True,
        default=None,
    )
    created_at = models.DateTimeField("создано", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "сообщение"
        verbose_name_plural = "сообщения"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("conversation", "external_message_id"),
                condition=~models.Q(external_message_id=""),
                name="supportchat_message_external_id_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_direction_display()}: {self.body[:40]}"


class SupportSchedule(models.Model):
    """Singleton working-hours schedule for support chat."""

    timezone: models.CharField = models.CharField(
        "часовой пояс",
        max_length=64,
        default="Europe/Moscow",
    )
    auto_reply_outside_hours: models.TextField = models.TextField(
        "автоответ вне часов",
        blank=True,
        default=("Спасибо за сообщение! Сейчас вне рабочего времени — ответим в ближайшие рабочие часы."),
    )
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        verbose_name = "расписание поддержки"
        verbose_name_plural = "расписание поддержки"

    def __str__(self) -> str:
        return f"Расписание ({self.timezone})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce singleton (pk=1)."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> SupportSchedule:
        """Return the singleton row, creating defaults if missing."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SupportScheduleDay(models.Model):
    """One weekday row (0=Monday … 6=Sunday)."""

    schedule = models.ForeignKey(
        SupportSchedule,
        on_delete=models.CASCADE,
        related_name="days",
        verbose_name="расписание",
    )
    weekday: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        "день недели",
        help_text="0=Пн … 6=Вс",
    )
    is_closed: models.BooleanField = models.BooleanField(
        "выходной",
        default=False,
    )

    class Meta:
        verbose_name = "день расписания"
        verbose_name_plural = "дни расписания"
        ordering = ("weekday",)
        constraints = [
            models.UniqueConstraint(
                fields=("schedule", "weekday"),
                name="supportchat_schedule_day_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0, weekday__lte=6),
                name="supportchat_schedule_weekday_range",
            ),
        ]

    def __str__(self) -> str:
        names = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        label = names[self.weekday] if 0 <= self.weekday <= 6 else str(self.weekday)
        return f"{label}{' (вых.)' if self.is_closed else ''}"


class SupportScheduleInterval(models.Model):
    """Open interval within a schedule day (supports lunch breaks)."""

    day = models.ForeignKey(
        SupportScheduleDay,
        on_delete=models.CASCADE,
        related_name="intervals",
        verbose_name="день",
    )
    start_time = models.TimeField("с")
    end_time = models.TimeField("по")

    class Meta:
        verbose_name = "интервал"
        verbose_name_plural = "интервалы"
        ordering = ("start_time",)

    def __str__(self) -> str:
        return f"{self.start_time}–{self.end_time}"


def touch_conversation_message(conversation: Conversation, *, inbound: bool) -> None:
    """Update last_message_at and staff unread counter."""
    conversation.last_message_at = timezone.now()
    if inbound:
        conversation.staff_unread_count = (conversation.staff_unread_count or 0) + 1
    conversation.save(update_fields=["last_message_at", "staff_unread_count", "updated_at"])
