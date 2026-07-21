"""Lead model for Hoocon CMS: RFQ / consultation / replacement (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead (RFQ / консультация / «подобрать замену»);
docs/readiness-backend-ux.md §2.2 (leads | Lead (RFQ / consult / replace));
docs/security-baseline.md §3 (PII-safe; validate; honeypot в Slice 19).

Заявка вместо корзины (B2B без онлайн-оплаты в v1). Три типа:
- RFQ: запрос КП (опц. sku + quantity для контекста).
- consultation: консультация (общий вопрос).
- replacement: подбор замены (опц. analog_belimo_code — Belimo артикул).

PII: name/email/phone — контактные данные; не логируем целиком (Slice 19).
`sku` — опц. FK с on_delete=SET_NULL (удаление SKU не удаляет заявку).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Lead(models.Model):
    """Customer inquiry (RFQ / consultation / replacement matching).

    Создаётся через публичный `POST /api/leads/` (Slice 19). Менеджер
    обрабатывает в Admin; статус ведёт от NEW → IN_PROGRESS → DONE.
    ``assignee`` — кто ведёт сейчас; ``processed_by`` — кто завершил.
    """

    class LeadType(models.TextChoices):
        RFQ = "rfq", "Запрос КП"
        CONSULTATION = "consultation", "Консультация"
        REPLACEMENT = "replacement", "Подбор замены"

    class LeadStatus(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Завершена"

    lead_type: models.CharField = models.CharField(
        "тип заявки",
        max_length=20,
        choices=LeadType.choices,
        default=LeadType.RFQ,
        db_index=True,
    )
    name: models.CharField = models.CharField("имя", max_length=200)
    email: models.EmailField = models.EmailField("эл. почта")
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
    )
    message: models.TextField = models.TextField("сообщение")
    sku: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="артикул (SKU)",
        help_text="SKU, по которому пришла заявка (опц.; SET_NULL при удалении SKU).",
    )
    quantity: models.PositiveIntegerField | None = models.PositiveIntegerField(
        "количество",
        null=True,
        blank=True,
        help_text="Количество (для RFQ).",
    )
    analog_belimo_code: models.CharField = models.CharField(
        "код аналога Belimo",
        max_length=100,
        blank=True,
        default="",
        help_text="Код аналога Belimo (для replacement).",
    )
    status: models.CharField = models.CharField(
        "статус",
        max_length=20,
        choices=LeadStatus.choices,
        default=LeadStatus.NEW,
        db_index=True,
    )
    client: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "crm.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="клиент CRM",
        help_text="Карточка клиента в CRM (создаётся автоматически при новой заявке).",
    )
    assignee: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
        verbose_name="в работе у",
        help_text="Менеджер, который сейчас ведёт заявку.",
        limit_choices_to={"is_staff": True},
    )
    processed_by: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_leads",
        verbose_name="обработал",
        help_text="Менеджер, который завершил обработку заявки.",
        limit_choices_to={"is_staff": True},
    )
    processed_at: models.DateTimeField | None = models.DateTimeField(
        "обработано",
        null=True,
        blank=True,
        db_index=True,
        help_text="Когда заявка была завершена (status=done).",
    )
    seen_at: models.DateTimeField | None = models.DateTimeField(
        "просмотрено",
        null=True,
        blank=True,
        db_index=True,
        help_text="Когда менеджер открыл заявку в Admin (стикер считает непросмотренные).",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        """Return Заявка #pk and type — no contact PII (safe for logs)."""
        return f"Заявка #{self.pk} ({self.get_lead_type_display()})"
