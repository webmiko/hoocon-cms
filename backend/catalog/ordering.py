"""Catalog list ordering helpers (category + numeric torque).

SKU ``sku_code`` is lexicographic (``da10…`` before ``da2…``). Cards must
sort by parsed ``moment`` AttributeValue ascending within each category.
"""

from __future__ import annotations

from typing import Any

from django.db.models import F, FloatField, Func, OuterRef, Q, Subquery, Value
from django.db.models.functions import Cast, NullIf, Replace
from django.db.models.query import QuerySet


class _RegexpReplace(Func):
    """Postgres ``REGEXP_REPLACE(source, pattern, replacement, flags)``."""

    function = "REGEXP_REPLACE"
    arity = 4


def _parse_moment_nm_expr(field_name: str = "value") -> Cast:
    """Extract the first number from a moment string (``5 Нм``, ``10``)."""
    extracted = _RegexpReplace(
        F(field_name),
        Value(r"^.*?([0-9]+(?:[.,][0-9]+)?).*$"),
        Value(r"\1"),
        Value("i"),
    )
    normalized = Replace(extracted, Value(","), Value("."))
    return Cast(NullIf(normalized, Value("")), FloatField())


def moment_nm_subquery() -> Subquery:
    """Numeric Нм from the SKU's moment AttributeValue (NULL if missing).

    Matches canonical ``slug=moment`` and legacy name-based rows
    (``Крутящий момент`` / ``Момент``).
    """
    from catalog.models import AttributeValue

    return Subquery(
        AttributeValue.objects.filter(sku_id=OuterRef("pk"))
        .filter(
            Q(attribute__slug="moment")
            | Q(attribute__name__icontains="крутящий момент")
            | Q(attribute__name__iexact="момент"),
        )
        .annotate(parsed=_parse_moment_nm_expr("value"))
        .order_by("id")
        .values("parsed")[:1],
        output_field=FloatField(),
    )


def annotate_moment_nm(queryset: QuerySet[Any]) -> QuerySet[Any]:
    """Annotate ``moment_nm`` FloatField (NULL when missing / unparsable)."""
    return queryset.annotate(moment_nm=moment_nm_subquery())


def catalog_list_order_by() -> tuple[Any, ...]:
    """Default catalog card order: category (spec) → moment ASC → sku_code.

    Within one category filter, ``category_spec_order`` is constant so cards
    sort purely by torque. Across all categories, sidebar order is preserved
    and torque applies inside each group. ``sku_code`` breaks ties only.
    """
    return (
        "category_spec_order",
        "product__category__name",
        F("moment_nm").asc(nulls_last=True),
        "sku_code",
    )
