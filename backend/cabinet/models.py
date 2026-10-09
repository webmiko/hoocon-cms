"""Client cabinet entities: spec templates, orders, RMA cases.

Plan: ``_docs/plan-client-cabinet-b2b.md`` §2.1 — ``cabinet.SpecList``,
``cabinet.Order``, ``cabinet.OrderItem``; §14.3 ЛК-12 (``RmaCase``),
ЛК-13 (трек-номер ТК на заказе), ЛК-11 (опциональная цена позиции).

Orders are manual (УНФ не интегрируем): менеджер ведёт статус в Admin.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.translation import gettext_lazy as _


class SpecList(models.Model):
    """Именованный шаблон позиций клиента («типовой набор для объекта X»)."""

    account = models.ForeignKey(
        "accounts.ClientAccount",
        on_delete=models.CASCADE,
        related_name="spec_lists",
        verbose_name=_("аккаунт"),
    )
    name = models.CharField(_("название набора"), max_length=200)
    note = models.CharField(_("заметка"), max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлён"))

    class Meta:
        verbose_name = _("спецификация")
        verbose_name_plural = _("спецификации")
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("account", "-updated_at"), name="account_spec_acct_upd_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} (#{self.pk})"


class SpecListItem(models.Model):
    """One SKU line inside a SpecList (snapshot survives SKU removal)."""

    spec = models.ForeignKey(
        SpecList,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("спецификация"),
    )
    sku = models.ForeignKey(
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spec_list_items",
        verbose_name=_("артикул (SKU)"),
    )
    sku_code = models.CharField(
        _("код артикула"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Снимок кода — переживает удаление SKU."),
    )
    quantity = models.PositiveIntegerField(_("количество"), default=1)
    position = models.PositiveIntegerField(_("порядок"), default=0)

    class Meta:
        verbose_name = _("позиция спецификации")
        verbose_name_plural = _("позиции спецификаций")
        ordering = ("position", "id")

    def __str__(self) -> str:
        sku = self.sku
        code = self.sku_code or (sku.sku_code if sku else "?")
        return f"{code} × {self.quantity}"


class OrderStatus(models.TextChoices):
    """Order lifecycle (manual mode — manager updates in Admin)."""

    ACCEPTED = "accepted", "Принят"
    IN_PRODUCTION = "in_production", "В производстве"
    READY = "ready", "Готов"
    SHIPPED = "shipped", "Отгружен"
    DONE = "done", "Завершён"
    CANCELLED = "cancelled", "Отменён"


class OrderCarrier(models.TextChoices):
    """Known transport companies for shipment tracking (ЛК-13)."""

    NONE = "", "—"
    DL = "dl", "Деловые Линии"
    SDEK = "sdek", "СДЭК"
    PEK = "pek", "ПЭК"
    OTHER = "other", "Другая"


class Order(models.Model):
    """Client order — согласованное КП, ведётся менеджером вручную.

    Separate entity (not a Lead status): заявка может породить несколько
    КП и заказов; смешение «обработки» и «производства» — антипаттерн.
    """

    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("клиент"),
    )
    quote = models.ForeignKey(
        "crm.Quote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("КП"),
        help_text=_("Согласованное КП, из которого вырос заказ."),
    )
    number = models.CharField(_("номер заказа / счёта"), max_length=60)
    status = models.CharField(
        _("статус"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.ACCEPTED,
        db_index=True,
    )
    progress = models.PositiveSmallIntegerField(
        _("готовность, %"),
        default=0,
        help_text=_("Опционально, 0–100."),
    )
    planned_ship_date = models.DateField(_("плановая отгрузка"), null=True, blank=True)
    carrier = models.CharField(
        _("транспортная компания"),
        max_length=20,
        choices=OrderCarrier.choices,
        default=OrderCarrier.NONE,
        blank=True,
    )
    track_number = models.CharField(_("трек-номер ТК"), max_length=100, blank=True, default="")
    external_id = models.CharField(
        _("id документа УНФ"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Задел под синк с 1С:УНФ (пока не интегрируем)."),
    )
    comment = models.TextField(_("комментарий"), blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлён"))

    class Meta:
        verbose_name = _("заказ")
        verbose_name_plural = _("заказы")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("client", "number"),
                name="account_order_client_number_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} · {self.client_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Clamp progress into 0–100."""
        if self.progress is not None:
            self.progress = max(0, min(100, self.progress))
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    """One SKU line on an order (snapshot + optional admin-only price)."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("заказ"),
    )
    sku = models.ForeignKey(
        "catalog.SKU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name=_("артикул (SKU)"),
    )
    sku_code = models.CharField(_("код артикула"), max_length=100, blank=True, default="")
    quantity = models.PositiveIntegerField(_("количество"), default=1)
    unit_price = models.DecimalField(
        _("цена за ед., ₽"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Только Admin; клиенту цены видны в PDF счёта."),
    )
    sort_order = models.PositiveSmallIntegerField(_("порядок"), default=0)

    class Meta:
        verbose_name = _("позиция заказа")
        verbose_name_plural = _("позиции заказа")
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        sku = self.sku
        code = self.sku_code or (sku.sku_code if sku else "?")
        return f"{code} × {self.quantity}"


def _private_media_storage() -> FileSystemStorage:
    """Storage outside public MEDIA_ROOT (owner/staff download only)."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def rma_photo_upload_to(instance: RmaCase, filename: str) -> str:
    """Store under ``rma_photos/<client_id>/<uuid>_<safe_name>`` (private)."""
    from catalog.validators import storage_safe_filename

    safe = storage_safe_filename(filename)
    return f"rma_photos/{instance.client_id}/{uuid.uuid4().hex}_{safe}"


class RmaStatus(models.TextChoices):
    """RMA (возврат/рекламация) lifecycle."""

    NEW = "new", "Новая"
    IN_REVIEW = "in_review", "На рассмотрении"
    ACCEPTED = "accepted", "Принята"
    REJECTED = "rejected", "Отклонена"
    RESOLVED = "resolved", "Решена"


class RmaCase(models.Model):
    """Клиентская рекламация: подаётся в ЛК, обрабатывается в Admin (ЛК-12)."""

    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.CASCADE,
        related_name="rma_cases",
        verbose_name=_("клиент"),
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rma_cases",
        verbose_name=_("заказ"),
    )
    serial_number = models.CharField(
        _("серийный номер"),
        max_length=100,
        blank=True,
        default="",
    )
    subject = models.CharField(_("тема"), max_length=300)
    description = models.TextField(_("описание проблемы"), blank=True, default="")
    photo = models.ImageField(
        _("фото дефекта"),
        upload_to=rma_photo_upload_to,
        storage=_private_media_storage,
        blank=True,
        default="",
        help_text=_("Приватное хранилище; скачивание только владельцем и персоналом."),
    )
    status = models.CharField(
        _("статус"),
        max_length=20,
        choices=RmaStatus.choices,
        default=RmaStatus.NEW,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлён"))

    class Meta:
        verbose_name = _("рекламация (RMA)")
        verbose_name_plural = _("рекламации (RMA)")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"RMA #{self.pk} · {self.subject}"
