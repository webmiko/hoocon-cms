"""CRM models: Client, Activity, EmailMessage."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone


class Client(models.Model):
    """B2B contact / company card for managers.

    ID = email (unique). Several Leads with the same email attach to one card
    (name/company used for search/filter and profile fill). See crm.services.
    """

    name: models.CharField = models.CharField("имя / контакт", max_length=200)
    email: models.EmailField = models.EmailField(
        "эл. почта",
        unique=True,
        db_index=True,
        help_text="Уникальный ключ карточки (нормализуется в нижний регистр).",
    )
    phone: models.CharField = models.CharField(
        "телефон",
        max_length=50,
        blank=True,
        default="",
    )
    phone_digits: models.CharField = models.CharField(
        "телефон (цифры)",
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="Нормализованные цифры — резолв звонков/писем по номеру.",
    )
    company: models.CharField = models.CharField(
        "компания",
        max_length=200,
        blank=True,
        default="",
        db_index=True,
    )
    company_key: models.CharField = models.CharField(
        "ключ компании",
        max_length=200,
        blank=True,
        default="",
        editable=False,
        db_index=True,
        help_text=(
            "Нормализованный ключ совпадения компании (как у закреплённых "
            "правил менеджеров). Заполняется автоматически."
        ),
    )
    notes: models.TextField = models.TextField(
        "заметки",
        blank=True,
        default="",
        help_text="Внутренние заметки менеджера (не для клиента).",
    )
    next_contact_at: models.DateTimeField | None = models.DateTimeField(
        "следующий контакт",
        null=True,
        blank=True,
        db_index=True,
        help_text="Напоминание менеджеру: просроченные даты видны РОПу в отчёте.",
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
    account: models.OneToOneField | None = models.OneToOneField(  # type: ignore[misc]
        "accounts.ClientAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_client",
        verbose_name="аккаунт ЛК",
        help_text="Владелец личного кабинета; v1: один логин = одна карточка (эл. почта = ключ).",
    )
    company_ref: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "crm.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
        verbose_name="компания (юрлицо)",
        help_text="Ссылка на карточку компании; текстовое поле «компания» остаётся для маршрутизации.",
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalize email (unique key), company_key and phone_digits."""
        from crm.telephony import normalize_phone_digits
        from leads.services import normalize_company_label

        self.email = (self.email or "").strip().lower()
        self.company_key = normalize_company_label(self.company)
        self.phone_digits = normalize_phone_digits(self.phone)
        super().save(*args, **kwargs)
        from crm.company import ensure_company_ref

        ensure_company_ref(self)

    def __str__(self) -> str:
        """Return email as ID, then name/company for Admin FK widgets."""
        if self.company:
            return f"{self.email} — {self.name} ({self.company})"
        return f"{self.email} — {self.name}"


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
    reply_to_email: models.EmailField = models.EmailField(
        "адрес для ответа",
        blank=True,
        default="",
        max_length=254,
    )
    subject: models.CharField = models.CharField("тема", max_length=300)
    body: models.TextField = models.TextField(
        "текст письма",
        max_length=20000,
        help_text="До 20 000 символов.",
    )
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
    message_id: models.CharField | None = models.CharField(
        "ID письма",
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text="Уникальный идентификатор письма (RFC-822): дедупликация и цепочки ответов.",
    )
    in_reply_to: models.CharField = models.CharField(
        "ответ на ID письма",
        max_length=255,
        blank=True,
        default="",
    )
    imap_uid: models.PositiveBigIntegerField | None = models.PositiveBigIntegerField(
        "UID в ящике (IMAP)",
        null=True,
        blank=True,
    )
    mailbox: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "accounts.StaffMailbox",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails",
        verbose_name="ящик",
        help_text="Личный ящик менеджера, через который пришло письмо (пусто — общий ящик).",
    )
    received_at: models.DateTimeField | None = models.DateTimeField(
        "получено (по дате письма)",
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


class EmailTemplate(models.Model):
    """Reusable subject/body preset for CRM compose forms.

    Placeholders ``{имя}``, ``{компания}``, ``{почта}``, ``{телефон}`` are
    substituted from the client card / lead contact when the template is
    applied (see ``crm.services.render_email_template``).
    """

    name: models.CharField = models.CharField(
        "название",
        max_length=200,
        help_text="Например: «Запрос реквизитов», «Напоминание о КП».",
    )
    subject: models.CharField = models.CharField(
        "тема",
        max_length=300,
        blank=True,
        default="",
        help_text="Плейсхолдеры {имя}, {компания}, {почта}, {телефон} подставляются автоматически.",
    )
    body: models.TextField = models.TextField(
        "текст письма",
        max_length=20000,
        help_text="Плейсхолдеры {имя}, {компания}, {почта}, {телефон} подставляются автоматически.",
    )
    is_active: models.BooleanField = models.BooleanField(
        "активен",
        default=True,
        db_index=True,
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        "порядок",
        default=0,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "шаблон письма"
        verbose_name_plural = "шаблоны писем"
        ordering = ("sort_order", "name")

    def __str__(self) -> str:
        """Template name for Admin lists."""
        return self.name


def _private_media_storage() -> FileSystemStorage:
    """Storage outside public MEDIA_ROOT (staff-only download via Admin)."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def email_attachment_upload_to(instance: EmailAttachment, filename: str) -> str:
    """Store under ``email_attachments/<email_id>/<uuid>_<safe_name>``.

    Filenames from mail are untrusted — sanitize; uuid part prevents
    collisions for repeated filenames in one message.
    """
    from catalog.validators import storage_safe_filename

    safe = storage_safe_filename(filename)
    return f"email_attachments/{instance.email_id}/{uuid.uuid4().hex}_{safe}"


class EmailAttachment(models.Model):
    """File attached to a CRM EmailMessage (private media, staff-only)."""

    email: models.ForeignKey = models.ForeignKey(
        EmailMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="письмо",
    )
    file: models.FileField = models.FileField(
        "файл",
        upload_to=email_attachment_upload_to,
        storage=_private_media_storage,
    )
    filename: models.CharField = models.CharField("имя файла", max_length=255)
    content_type: models.CharField = models.CharField(
        "тип содержимого",
        max_length=100,
        blank=True,
        default="",
    )
    size: models.PositiveIntegerField = models.PositiveIntegerField(
        "размер, байт",
        default=0,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "вложение письма"
        verbose_name_plural = "вложения писем"
        ordering = ("created_at",)

    def __str__(self) -> str:
        """Return filename for Admin."""
        return self.filename


class InboundMailboxState(models.Model):
    """Singleton: IMAP cursor + health for ``crm.fetch_inbound_email``."""

    folder: models.CharField = models.CharField("папка", max_length=100, default="INBOX")
    last_uid: models.PositiveBigIntegerField = models.PositiveBigIntegerField(
        "последний обработанный UID",
        default=0,
    )
    last_run_at: models.DateTimeField | None = models.DateTimeField(
        "последний запуск",
        null=True,
        blank=True,
    )
    last_error: models.CharField = models.CharField(
        "последняя ошибка",
        max_length=300,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "ящик входящих (IMAP)"
        verbose_name_plural = "ящик входящих (IMAP)"

    def __str__(self) -> str:
        """Return folder + cursor for Admin."""
        return f"{self.folder} uid>{self.last_uid}"

    @classmethod
    def get_solo(cls) -> InboundMailboxState:
        """Return the single cursor row (created on first use)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class QuoteStatus(models.TextChoices):
    """Lifecycle of a commercial offer."""

    DRAFT = "draft", "Черновик"
    SENT = "sent", "Выдано"
    ACCEPTED = "accepted", "Согласовано"
    REJECTED = "rejected", "Отклонено"


# Draft → Accepted/Rejected skips the PDF and the client email, so a quote
# must be issued first. Back to draft only from «Выдано» (recall to fix).
QUOTE_TRANSITIONS: dict[str, frozenset[str]] = {
    QuoteStatus.DRAFT: frozenset({QuoteStatus.SENT}),
    QuoteStatus.SENT: frozenset({QuoteStatus.DRAFT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED}),
    QuoteStatus.ACCEPTED: frozenset({QuoteStatus.SENT, QuoteStatus.REJECTED}),
    QuoteStatus.REJECTED: frozenset({QuoteStatus.SENT, QuoteStatus.ACCEPTED}),
}


def quote_transition_allowed(current: str, target: str) -> bool:
    """True when ``current`` → ``target`` is a legal КП status move (same = no-op)."""
    return current == target or target in QUOTE_TRANSITIONS.get(current, frozenset())


class Quote(models.Model):
    """Коммерческое предложение — результат обработки заявки.

    Создаётся кнопкой «Создать КП» из карточки заявки (позиции
    копируются из ``LeadItem``). Перевод в ``SENT`` автозакрывает
    заявку: заявка — вход воронки, КП — её результат.
    """

    client: models.ForeignKey = models.ForeignKey(  # type: ignore[misc]
        Client,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name="клиент",
    )
    lead: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        verbose_name="заявка",
        help_text="Заявка, из которой выдано КП (закрывается при «Выдано»).",
    )
    number: models.CharField = models.CharField(
        "номер",
        max_length=30,
        unique=True,
        blank=True,
        default="",
        help_text="Проставляется автоматически (КП-<id>).",
    )
    status: models.CharField = models.CharField(
        "статус",
        max_length=20,
        choices=QuoteStatus.choices,
        default=QuoteStatus.DRAFT,
        db_index=True,
    )
    comment: models.TextField = models.TextField(
        "комментарий",
        blank=True,
        default="",
        help_text="Условия КП: сроки, доставка, особые договорённости.",
    )
    valid_until: models.DateField | None = models.DateField(
        "действует до",
        null=True,
        blank=True,
        help_text="Пусто при создании — +14 дней от сегодня.",
    )
    vat_rate: models.DecimalField = models.DecimalField(
        "НДС, %",
        max_digits=5,
        decimal_places=2,
        default=Decimal("22.00"),
        help_text="Ставка НДС в PDF. 0 — не показывать строку НДС.",
    )
    created_by: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_quotes_created",
        verbose_name="менеджер",
    )
    sent_at: models.DateTimeField | None = models.DateTimeField(
        "выдано",
        null=True,
        blank=True,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "коммерческое предложение"
        verbose_name_plural = "коммерческие предложения"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        """Human label: number + client."""
        return f"{self.number or f'КП-{self.pk}'} · {self.client}"

    def clean(self) -> None:
        """Reject illegal status moves on Admin edit (see ``QUOTE_TRANSITIONS``)."""
        super().clean()
        if self.pk is None:
            return
        current = Quote.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        if current is not None and not quote_transition_allowed(current, self.status):
            source, target = QuoteStatus(current).label, QuoteStatus(self.status).label
            raise ValidationError({"status": f"Нельзя перевести КП из «{source}» в «{target}»."})

    def save(self, *args: object, **kwargs: object) -> None:
        """Assign sequential number and default validity on first save."""
        if self._state.adding and self.valid_until is None:
            self.valid_until = timezone.localdate() + timedelta(days=14)
        super().save(*args, **kwargs)  # type: ignore[arg-type]
        if not self.number:
            self.number = f"КП-{self.pk}"
            super().save(update_fields=["number"])  # type: ignore[arg-type]


class QuoteItem(models.Model):
    """One SKU line on a quote (snapshot like LeadItem + optional price)."""

    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="КП",
    )
    sku = models.ForeignKey(
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_items",
        verbose_name="артикул (SKU)",
    )
    sku_code: models.CharField = models.CharField(
        "код артикула",
        max_length=100,
        blank=True,
        default="",
        help_text="Снимок кода на момент КП (если SKU сняли с публикации).",
    )
    quantity: models.PositiveIntegerField = models.PositiveIntegerField(
        "количество",
        default=1,
    )
    unit_price: models.DecimalField | None = models.DecimalField(
        "цена за ед., ₽",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Необязательно. Цены видны только менеджеру и в счёте.",
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        "порядок",
        default=0,
    )

    class Meta:
        verbose_name = "позиция КП"
        verbose_name_plural = "позиции КП"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        """Short line for Admin."""
        code = self.sku_code or (self.sku.sku_code if self.sku else "?")
        return f"{code} × {self.quantity}"


def client_document_upload_to(instance: ClientDocument, filename: str) -> str:
    """Store under ``client_docs/<client_id>/<uuid>_<safe_name>`` (private)."""
    from catalog.validators import storage_safe_filename

    safe = storage_safe_filename(filename)
    return f"client_docs/{instance.client_id}/{uuid.uuid4().hex}_{safe}"


class DocumentKind(models.TextChoices):
    """Client-visible document types (ЛК-3 документы + ЛК-14 счёта/УПД)."""

    QUOTE_PDF = "quote_pdf", "КП (PDF)"
    INVOICE = "invoice", "Счёт"
    SPEC = "spec", "Спецификация"
    UPD = "upd", "УПД"
    OTHER = "other", "Прочее"


class EdoStatus(models.TextChoices):
    """ЭДО signing status — ручное поле до API-синка (решение 2026-10)."""

    NONE = "", "—"
    SENT = "sent", "Отправлен в ЭДО"
    SIGNED = "signed", "Подписан"
    REJECTED = "rejected", "Отклонён"


class ClientDocument(models.Model):
    """File shown to the client in the cabinet (private media, owner-only).

    Менеджер грузит в карточке клиента; PDF КП прикрепляется автоматически
    при выдаче КП (см. ``crm.quote_pdf``). Download — только через
    проверенный endpoint (Admin для staff, ``/api/account/documents/`` для
    владельца), файлы вне public ``MEDIA_ROOT``.
    """

    client: models.ForeignKey = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="клиент",
    )
    quote: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        Quote,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="КП",
    )
    order: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "cabinet.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="заказ",
    )
    kind: models.CharField = models.CharField(
        "тип",
        max_length=20,
        choices=DocumentKind.choices,
        default=DocumentKind.OTHER,
        db_index=True,
    )
    file: models.FileField = models.FileField(
        "файл",
        upload_to=client_document_upload_to,
        storage=_private_media_storage,
    )
    title: models.CharField = models.CharField("название", max_length=300)
    edo_status: models.CharField = models.CharField(
        "статус ЭДО",
        max_length=20,
        choices=EdoStatus.choices,
        default=EdoStatus.NONE,
        blank=True,
        help_text="Ручной статус подписания; API-синк ЭДО — позже.",
    )
    uploaded_by: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_documents_uploaded",
        verbose_name="загрузил",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "документ клиента"
        verbose_name_plural = "документы клиента"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title or f"Документ #{self.pk}"


class Company(models.Model):
    """Юрлицо/компания клиента — целевая сущность для мульти-аккаунта (CRM-x).

    v1: карточка Client живёт по email; Company держит реквизиты и членов
    (CompanyMember), чтобы не мигрировать привязку дважды.
    ``company_key`` матчится тем же нормализатором, что и правила
    закрепления менеджеров и ``Client.company_key``.
    """

    name: models.CharField = models.CharField("название", max_length=200)
    company_key: models.CharField = models.CharField(
        "ключ компании",
        max_length=200,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Нормализованный ключ совпадения (заполняется автоматически).",
    )
    inn: models.CharField = models.CharField(
        "ИНН",
        max_length=12,
        blank=True,
        default="",
        db_index=True,
    )
    legal_address: models.CharField = models.CharField(
        "юридический адрес",
        max_length=400,
        blank=True,
        default="",
    )
    comment: models.TextField = models.TextField("комментарий", blank=True, default="")
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "компания"
        verbose_name_plural = "компании"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalize company_key from the display name."""
        from leads.services import normalize_company_label

        self.company_key = normalize_company_label(self.name)
        super().save(*args, **kwargs)


class CompanyMemberRole(models.TextChoices):
    """Member role inside a company (мульти-сотрудники, целевая схема)."""

    BUYER = "buyer", "Закупщик"
    ENGINEER = "engineer", "Инженер"
    ADMIN = "admin", "Администратор"


class CompanyMember(models.Model):
    """Member of a Company: linked Client card + optional cabinet cabinet."""

    company: models.ForeignKey = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="компания",
    )
    client: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_memberships",
        verbose_name="карточка клиента",
    )
    account: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "accounts.ClientAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_memberships",
        verbose_name="аккаунт ЛК",
    )
    role: models.CharField = models.CharField(
        "роль",
        max_length=20,
        choices=CompanyMemberRole.choices,
        default=CompanyMemberRole.BUYER,
    )
    is_confirmed: models.BooleanField = models.BooleanField(
        "подтверждён менеджером",
        default=False,
        help_text="Только подтверждённые сотрудники видят ИНН, адрес и состав компании в кабинете. "
        "Связь по названию из заявки создаётся неподтверждённой.",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "сотрудник компании"
        verbose_name_plural = "сотрудники компаний"
        ordering = ("company", "id")

    def __str__(self) -> str:
        label = self.client or self.account or "—"
        return f"{self.company} · {label} ({self.get_role_display()})"


class CallDirection(models.TextChoices):
    """Who initiated the call."""

    INBOUND = "inbound", "Входящий"
    OUTBOUND = "outbound", "Исходящий"


class CallState(models.TextChoices):
    """Lifecycle of a call leg reported by Mango events."""

    APPEARED = "appeared", "Появился"
    CONNECTED = "connected", "Соединён"
    DISCONNECTED = "disconnected", "Завершён"
    ON_HOLD = "on_hold", "На удержании"
    TRANSFERRED = "transferred", "Переведён"
    INITIATED = "initiated", "Инициирован"


def call_recording_upload_to(instance: Call, filename: str) -> str:
    """Recordings under ``call_recordings/<entry_id>_<uuid>`` (private media)."""
    return f"call_recordings/{instance.entry_id}_{uuid.uuid4().hex}.mp3"


class Call(models.Model):
    """Phone call leg tracked via Mango VPBX webhooks.

    ``entry_id`` is Mango's stable call identifier — repeated events for the
    same call update this row (dedup by unique key). ``call_id`` may differ
    per leg; kept for diagnostics and callback-command correlation.
    """

    entry_id: models.CharField = models.CharField(
        "ID вызова Mango",
        max_length=128,
        unique=True,
        db_index=True,
    )
    call_id: models.CharField = models.CharField(
        "ID звонка Mango",
        max_length=200,
        blank=True,
        default="",
        db_index=True,
    )
    direction: models.CharField = models.CharField(
        "направление",
        max_length=10,
        choices=CallDirection.choices,
        default=CallDirection.INBOUND,
    )
    state: models.CharField = models.CharField(
        "состояние",
        max_length=15,
        choices=CallState.choices,
        default=CallState.APPEARED,
    )
    from_number: models.CharField = models.CharField("откуда", max_length=32, blank=True, default="")
    to_number: models.CharField = models.CharField("куда", max_length=32, blank=True, default="")
    extension: models.CharField = models.CharField(
        "добавочный",
        max_length=20,
        blank=True,
        default="",
        help_text="Внутренний номер менеджера в АТС.",
    )
    client: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calls",
        verbose_name="клиент",
    )
    lead: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calls",
        verbose_name="заявка",
    )
    manager = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calls",
        verbose_name="менеджер",
        help_text="Определяется по добавочному (профиль АТС на странице пользователя).",
    )
    started_at: models.DateTimeField = models.DateTimeField("начало", null=True, blank=True)
    connected_at: models.DateTimeField = models.DateTimeField("соединён", null=True, blank=True)
    finished_at: models.DateTimeField = models.DateTimeField("завершён", null=True, blank=True)
    talk_duration: models.PositiveIntegerField = models.PositiveIntegerField(
        "длительность разговора, сек",
        default=0,
    )
    recording_id: models.CharField = models.CharField(
        "ID записи Mango",
        max_length=200,
        blank=True,
        default="",
    )
    recording: models.FileField = models.FileField(
        "запись разговора",
        upload_to=call_recording_upload_to,
        storage=_private_media_storage,
        blank=True,
        default="",
    )
    last_seq: models.PositiveIntegerField = models.PositiveIntegerField(
        "№ последнего события",
        default=0,
        help_text="События Mango идут по порядку; устаревшие отбрасываем.",
    )
    created_at: models.DateTimeField = models.DateTimeField("создан", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        verbose_name = "звонок"
        verbose_name_plural = "звонки"
        ordering = ("-started_at", "-id")
        indexes = [
            models.Index(fields=("from_number",)),
            models.Index(fields=("to_number",)),
            models.Index(fields=("extension",)),
        ]

    def __str__(self) -> str:
        arrow = "→" if self.direction == CallDirection.OUTBOUND else "←"
        when = timezone.localtime(self.started_at or self.created_at)
        return f"{self.from_number or '?'} {arrow} {self.to_number or '?'} · {when:%d.%m %H:%M}"
