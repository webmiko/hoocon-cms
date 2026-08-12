"""Lead model for Hoocon CMS: RFQ / consultation / replacement (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead (RFQ / консультация / «подобрать замену»);
docs/readiness-backend-ux.md §2.2 (leads | Lead (RFQ / consult / replace));
docs/security-baseline.md §3 (PII-safe; validate; honeypot в Slice 19).

Заявка вместо корзины (B2B без онлайн-оплаты в v1). Три типа:
- RFQ: запрос КП (позиции LeadItem; legacy sku + quantity — сводка).
- consultation: консультация (общий вопрос).
- replacement: подбор замены (опц. analog_belimo_code — Belimo артикул).

RFQ soft-bundle: заявки с одной нормализованной парой компания+имя
связываются через ``rfq_bundle_key`` / ``rfq_bundle_root`` (без hard-merge).

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
        help_text="Для запроса КП обязательна: ключ нити КП = компания + имя.",
    )
    message: models.TextField = models.TextField("сообщение")
    sku: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="артикул (SKU)",
        help_text=("Сводка: первый артикул из позиций (необязательно; при удалении артикула связь обнуляется)."),
    )
    quantity: models.PositiveIntegerField | None = models.PositiveIntegerField(
        "количество",
        null=True,
        blank=True,
        help_text="Сводка: количество по первому артикулу (RFQ).",
    )
    analog_belimo_code: models.CharField = models.CharField(
        "код аналога Belimo",
        max_length=100,
        blank=True,
        default="",
        help_text="Код аналога Belimo (для заявок на замену).",
    )
    rfq_bundle_key: models.CharField = models.CharField(
        "ключ нити КП",
        max_length=400,
        blank=True,
        default="",
        db_index=True,
        help_text="Нормализованные компания|имя для мягкой группировки RFQ.",
    )
    rfq_bundle_root = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rfq_bundle_children",
        verbose_name="корень нити КП",
        help_text="Первая открытая заявка нити; у корня пусто.",
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
        help_text="Когда заявка была завершена (статус «Завершена»).",
    )
    seen_at: models.DateTimeField | None = models.DateTimeField(
        "просмотрено",
        null=True,
        blank=True,
        db_index=True,
        help_text=("Когда менеджер открыл заявку в админке (стикер считает непросмотренные)."),
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


class LeadItem(models.Model):
    """One SKU line on a lead (multi-SKU RFQ)."""

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="заявка",
    )
    sku = models.ForeignKey(
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_items",
        verbose_name="артикул (SKU)",
    )
    sku_code: models.CharField = models.CharField(
        "код артикула",
        max_length=100,
        blank=True,
        default="",
        help_text="Снимок кода на момент заявки (если SKU сняли с публикации).",
    )
    quantity: models.PositiveIntegerField = models.PositiveIntegerField(
        "количество",
        default=1,
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        "порядок",
        default=0,
    )

    class Meta:
        verbose_name = "позиция заявки"
        verbose_name_plural = "позиции заявки"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        """Short line for Admin."""
        if self.sku_code:
            code = self.sku_code
        elif self.sku is not None:
            code = self.sku.sku_code
        else:
            code = "?"
        return f"{code} × {self.quantity}"
