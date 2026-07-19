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

from django.db import models


class Lead(models.Model):
    """Customer inquiry (RFQ / consultation / replacement matching).

    Создаётся через публичный `POST /api/leads/` (Slice 19). Менеджер
    обрабатывает в Admin; статус ведёт от NEW → IN_PROGRESS → DONE.

    Args (fields):
        lead_type: rfq | consultation | replacement (default rfq).
        name: контактное имя (обязательное).
        email: контактный email (обязательный).
        phone: опц. телефон.
        company: опц. компания.
        message: текст заявки (обязательный).
        sku: опц. FK на SKU (контекст для RFQ; SET_NULL при удалении SKU).
        quantity: опц. количество (для RFQ).
        analog_belimo_code: опц. код аналога Belimo (для replacement).
        status: new | in_progress | done (default new; staff-only).
        created_at / updated_at: авто-таймстампы.
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
        max_length=20,
        choices=LeadType.choices,
        default=LeadType.RFQ,
        db_index=True,
    )
    name: models.CharField = models.CharField(max_length=200)
    email: models.EmailField = models.EmailField()
    phone: models.CharField = models.CharField(max_length=50, blank=True, default="")
    company: models.CharField = models.CharField(max_length=200, blank=True, default="")
    message: models.TextField = models.TextField()
    sku: models.ForeignKey | None = models.ForeignKey(  # type: ignore[misc]
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        help_text="SKU, по которому пришла заявка (опц.; SET_NULL при удалении SKU).",
    )
    quantity: models.PositiveIntegerField | None = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Количество (для RFQ).",
    )
    analog_belimo_code: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Код аналога Belimo (для replacement).",
    )
    status: models.CharField = models.CharField(
        max_length=20,
        choices=LeadStatus.choices,
        default=LeadStatus.NEW,
        db_index=True,
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        """Return 'name (lead_type)' for Admin and logs (no PII in str)."""
        return f"{self.name} ({self.get_lead_type_display()})"
