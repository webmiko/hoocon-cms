"""Queue of manager requests. Off by default until an admin enables the widget."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class StaffRequestKind(models.TextChoices):
    """What the manager is asking for."""

    BUG = "bug", "Баг"
    IMPROVEMENT = "improvement", "Доработка"
    QUESTION = "question", "Вопрос"
    ASK = "ask", "Просьба"


class StaffRequestStatus(models.TextChoices):
    """Admin-owned lifecycle. Managers do not move these."""

    NEW = "new", "Новое"
    IN_PROGRESS = "in_progress", "В работе"
    WAITING = "waiting", "Жду ответ"
    DONE = "done", "Сделано"
    REJECTED = "rejected", "Отклонено"


class StaffRequestSettings(models.Model):
    """Singleton switch. The queue stays in the database when this is off."""

    SINGLETON_PK = 1

    enabled = models.BooleanField("включён", default=False)

    class Meta:
        verbose_name = "настройка техподдержки"
        verbose_name_plural = "настройка техподдержки"

    def __str__(self) -> str:
        return "Техподдержка включена" if self.enabled else "Техподдержка выключена"

    def save(self, *args: object, **kwargs: object) -> None:
        """Keep a single row."""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        """The switch row is not removed; turn the widget off instead."""
        return (0, {})

    @classmethod
    def load(cls) -> StaffRequestSettings:
        """Return the singleton, creating it switched off."""
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj


class StaffRequest(models.Model):
    """One request from a staff user to the admin queue."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_requests",
        verbose_name="автор",
    )
    kind = models.CharField(
        "тип",
        max_length=20,
        choices=StaffRequestKind.choices,
        default=StaffRequestKind.QUESTION,
    )
    title = models.CharField("тема", max_length=200)
    body = models.TextField("текст")
    status = models.CharField(
        "статус",
        max_length=20,
        choices=StaffRequestStatus.choices,
        default=StaffRequestStatus.NEW,
        db_index=True,
    )
    closed_at = models.DateTimeField("закрыто", null=True, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "запрос"
        verbose_name_plural = "запросы"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("author", "status")),
        ]

    def __str__(self) -> str:
        return self.title


class StaffRequestReply(models.Model):
    """A message on a request. Author is the person who wrote this reply."""

    ticket = models.ForeignKey(
        StaffRequest,
        on_delete=models.CASCADE,
        related_name="replies",
        verbose_name="запрос",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_request_replies",
        verbose_name="автор",
    )
    body = models.TextField("текст")
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "ответ"
        verbose_name_plural = "ответы"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"Ответ #{self.pk}"
