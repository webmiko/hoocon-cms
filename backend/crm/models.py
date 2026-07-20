"""CRM models: Client, Activity, EmailMessage."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Client(models.Model):
    """B2B contact / company card for managers.

    Deduped primarily by email. Leads can be linked via Lead.client.
    """

    name: models.CharField = models.CharField("имя / контакт", max_length=200)
    email: models.EmailField = models.EmailField("email", db_index=True)
    phone: models.CharField = models.CharField(
        "телефон",
        max_length=50,
        blank=True,
        default="",
    )
    company: models.CharField = models.CharField(
        "компания",
        max_length=200,
        blank=True,
        default="",
        db_index=True,
    )
    notes: models.TextField = models.TextField(
        "заметки",
        blank=True,
        default="",
        help_text="Внутренние заметки менеджера (не для клиента).",
    )
    assignee: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_clients",
        verbose_name="ответственный",
        limit_choices_to={"is_staff": True},
    )
    is_active: models.BooleanField = models.BooleanField(
        "активен",
        default=True,
        db_index=True,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "клиент"
        verbose_name_plural = "клиенты"
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("email", "company")),
        ]

    def __str__(self) -> str:
        """Return 'name (company)' or email for Admin."""
        if self.company:
            return f"{self.name} — {self.company}"
        return f"{self.name} <{self.email}>"


class ActivityType(models.TextChoices):
    """Kinds of CRM activities."""

    NOTE = "note", "Заметка"
    CALL = "call", "Звонок"
    EMAIL = "email", "Письмо"
    STATUS = "status", "Смена статуса"
    OTHER = "other", "Прочее"


class Activity(models.Model):
    """Timeline entry on a Client (and optional Lead)."""

    client: models.ForeignKey = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name="клиент",
    )
    lead: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_activities",
        verbose_name="заявка",
    )
    activity_type: models.CharField = models.CharField(
        "тип",
        max_length=20,
        choices=ActivityType.choices,
        default=ActivityType.NOTE,
        db_index=True,
    )
    subject: models.CharField = models.CharField(
        "тема",
        max_length=300,
        blank=True,
        default="",
    )
    body: models.TextField = models.TextField("текст", blank=True, default="")
    author: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_activities",
        verbose_name="автор",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "активность"
        verbose_name_plural = "активности"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        """Return type + subject for Admin."""
        label = self.get_activity_type_display()
        if self.subject:
            return f"{label}: {self.subject}"
        return f"{label} #{self.pk}"


class EmailDirection(models.TextChoices):
    """Inbound vs outbound mail."""

    OUTBOUND = "outbound", "Исходящее"
    INBOUND = "inbound", "Входящее"


class EmailStatus(models.TextChoices):
    """Delivery status for CRM emails."""

    DRAFT = "draft", "Черновик"
    QUEUED = "queued", "В очереди"
    SENT = "sent", "Отправлено"
    FAILED = "failed", "Ошибка"
    RECEIVED = "received", "Получено"


class EmailMessage(models.Model):
    """Email linked to a CRM Client (outbound from Admin; inbound later)."""

    client: models.ForeignKey = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="emails",
        verbose_name="клиент",
    )
    lead: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_emails",
        verbose_name="заявка",
    )
    direction: models.CharField = models.CharField(
        "направление",
        max_length=20,
        choices=EmailDirection.choices,
        default=EmailDirection.OUTBOUND,
        db_index=True,
    )
    status: models.CharField = models.CharField(
        "статус",
        max_length=20,
        choices=EmailStatus.choices,
        default=EmailStatus.DRAFT,
        db_index=True,
    )
    to_email: models.EmailField = models.EmailField("кому")
    from_email: models.EmailField = models.EmailField(
        "от кого",
        blank=True,
        default="",
    )
    subject: models.CharField = models.CharField("тема", max_length=300)
    body: models.TextField = models.TextField("текст письма")
    error_message: models.TextField = models.TextField(
        "ошибка",
        blank=True,
        default="",
    )
    created_by: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_emails_created",
        verbose_name="создал",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    sent_at: models.DateTimeField | None = models.DateTimeField(
        "отправлено",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "письмо"
        verbose_name_plural = "письма"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        """Return subject + status for Admin."""
        return f"{self.subject} ({self.get_status_display()})"

    def mark_sent(self) -> None:
        """Mark as successfully sent."""
        self.status = EmailStatus.SENT
        self.error_message = ""
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "error_message", "sent_at"])

    def mark_failed(self, error: str) -> None:
        """Mark as failed with a truncated error."""
        self.status = EmailStatus.FAILED
        self.error_message = error[:2000]
        self.save(update_fields=["status", "error_message"])
