"""Normalize catalog texts to Belimo RU terminology (docs/tech-copy-belimo-ru.md)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.tech_copy import (
    normalize_control_attribute_value,
    normalize_modulating_signal_value,
    normalize_running_time_value,
    normalize_tech_copy,
    normalize_voltage_attribute_value,
)
from catalog.facets import (
    FACET_BY_KEY,
    attribute_matches_facet,
    ensure_modulating_signal_attributes,
    normalize_area_attribute_value,
    normalize_aux_switch_value,
)
from catalog.models import SKU, AttributeValue, Category, Product
from catalog.sku_access import sku_category_slug

# Re-export for existing imports (tests / callers).
__all__ = ("Command", "sku_category_slug")


class Command(BaseCommand):
    """Rewrite Category / Product / SKU / AttributeValue copy to glossary style."""

    help = (
        "Normalize tech copy: плавное→пропорциональное (модулирующее), "
        "VDC→В=, класс защиты IP→степень защиты корпуса, напряжение→Belimo, "
        "Y/U сигнал без дубля «заводская 0...10 В=», и т.д."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts without saving.",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run"))
        updated = {
            "category": 0,
            "product": 0,
            "sku": 0,
            "attribute_value": 0,
            "modulating_signals": 0,
        }

        with transaction.atomic():
            updated["category"] = self._normalize_model(
                Category.objects.all(),
                ("name", "description", "instructions"),
                dry_run=dry_run,
            )
            updated["product"] = self._normalize_model(
                Product.objects.all(),
                (
                    "name",
                    "description",
                    "instructions",
                    "specs_text",
                    "analogs_text",
                ),
                dry_run=dry_run,
            )
            updated["sku"] = self._normalize_model(
                SKU.objects.all(),
                ("name", "description", "specs_text", "analogs_text"),
                dry_run=dry_run,
            )
            updated["attribute_value"] = self._normalize_attributes(dry_run=dry_run)
            updated["modulating_signals"] = self._ensure_modulating_signals(
                dry_run=dry_run,
            )
            if dry_run:
                transaction.set_rollback(True)

        style = self.style.WARNING if dry_run else self.style.SUCCESS
        mode = "dry-run" if dry_run else "saved"
        self.stdout.write(
            style(
                f"Tech copy normalize ({mode}): "
                f"categories={updated['category']}, "
                f"products={updated['product']}, "
                f"skus={updated['sku']}, "
                f"attribute_values={updated['attribute_value']}, "
                f"modulating_signals={updated['modulating_signals']}",
            ),
        )

    def _normalize_model(
        self,
        queryset,
        fields: tuple[str, ...],
        *,
        dry_run: bool,
    ) -> int:
        count = 0
        for obj in queryset.iterator():
            changed: list[str] = []
            for field in fields:
                raw = getattr(obj, field, "") or ""
                if not raw:
                    continue
                new = normalize_tech_copy(raw)
                if new != raw:
                    setattr(obj, field, new)
                    changed.append(field)
            if changed:
                count += 1
                if not dry_run:
                    obj.save(update_fields=changed)
        return count

    def _normalize_attributes(self, *, dry_run: bool) -> int:
        count = 0
        voltage_facet = FACET_BY_KEY["voltage"]
        aux_facet = FACET_BY_KEY["aux_switch"]
        area_facet = FACET_BY_KEY["area"]
        signal_slugs = frozenset({"control-signal", "feedback-signal"})
        qs = AttributeValue.objects.select_related(
            "attribute",
            "sku",
            "sku__product__category",
        ).iterator()
        for av in qs:
            name = (av.attribute.name or "").casefold()
            slug = (av.attribute.slug or "").casefold()
            raw = av.value or ""
            if slug in signal_slugs or "обратная связь" in name:
                new = normalize_modulating_signal_value(raw)
            elif "управляющий сигнал" in name or "сигнал управления" in name:
                new = normalize_modulating_signal_value(raw)
            elif "управл" in name:
                new = normalize_control_attribute_value(
                    raw,
                    sku_code=av.sku.sku_code if av.sku_id else None,
                    category_slug=sku_category_slug(av.sku if av.sku_id else None),
                )
            elif attribute_matches_facet(av.attribute, voltage_facet):
                new = normalize_voltage_attribute_value(
                    raw,
                    sku_code=av.sku.sku_code if av.sku_id else None,
                )
            elif attribute_matches_facet(av.attribute, area_facet):
                new = normalize_area_attribute_value(raw)
            elif attribute_matches_facet(av.attribute, aux_facet):
                new = normalize_aux_switch_value(
                    raw,
                    sku_code=av.sku.sku_code if av.sku_id else None,
                    description=(av.sku.description or "") if av.sku_id else "",
                )
            elif "время поворота" in name or "время срабатывания" in name:
                new = normalize_running_time_value(raw)
            else:
                new = normalize_tech_copy(raw)
            if new != raw:
                count += 1
                if not dry_run:
                    av.value = new
                    av.save(update_fields=["value"])
        return count

    def _ensure_modulating_signals(self, *, dry_run: bool) -> int:
        """Create Y/U signal EAV for пропорциональное SKUs (Belimo RU)."""
        count = 0
        qs = SKU.objects.select_related("product__category").prefetch_related(
            "attribute_values__attribute",
        )
        for sku in qs.iterator(chunk_size=50):
            # Count potential changes without skipping dry-run persistence:
            # ensure_* writes; for dry-run wrap is rolled back by caller.
            if dry_run:
                from catalog.etl.tech_copy import (
                    is_proportional_control,
                    normalize_control_attribute_value,
                )
                from catalog.facets import FACET_BY_KEY, attribute_matches_facet

                control_raw = ""
                for av in sku.attribute_values.all():
                    if attribute_matches_facet(av.attribute, FACET_BY_KEY["control"]):
                        control_raw = str(av.value or "")
                        break
                control = normalize_control_attribute_value(
                    control_raw,
                    sku_code=sku.sku_code,
                    category_slug=sku_category_slug(sku),
                )
                if is_proportional_control(control):
                    count += 2
                continue
            count += ensure_modulating_signal_attributes(sku)
        return count
