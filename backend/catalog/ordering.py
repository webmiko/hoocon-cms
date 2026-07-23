"""Catalog list ordering helpers (category + numeric torque / article).

SKU ``sku_code`` is lexicographic (``da10…`` before ``da2…``). Cards sort by
parsed ``moment`` AttributeValue ascending within each category, with a
numeric fallback extracted from the article when moment is missing (ball
valves DN, etc.).
"""

from __future__ import annotations

from typing import Any

from django.db.models import F, FloatField, Func, OuterRef, Q, Subquery, Value
from django.db.models.functions import Cast, Coalesce, NullIf, Replace
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


def _parse_sku_code_nm_expr() -> Cast:
    """Numeric key from ``sku_code`` (DA/SA/BV torque or DN, else trailing -N).

    Examples:
        ``DA10FU24-D`` → 10, ``8100-bv215a`` → 215, ``HVA230-5Q`` → 5.

    Postgres ``REGEXP_REPLACE`` returns the whole string when the pattern does
    not match; ``NullIf(..., sku_code)`` drops those misses. Use flag ``i``
    (ARE); do not embed ``(?i)`` — that breaks POSIX mode.
    """
    family_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^(8100-)?(da|sa|bv)([0-9]+).*$"),
        Value(r"\3"),
        Value("i"),
    )
    trail_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^.*-([0-9]+)[a-z]*$"),
        Value(r"\1"),
        Value("i"),
    )
    picked = Coalesce(
        NullIf(family_or_raw, F("sku_code")),
        NullIf(trail_or_raw, F("sku_code")),
        Value(""),
    )
    return Cast(NullIf(picked, Value("")), FloatField())


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
    """Annotate ``moment_nm`` and ``sku_code_nm`` for catalog ordering."""
    return queryset.annotate(
        moment_nm=moment_nm_subquery(),
        sku_code_nm=_parse_sku_code_nm_expr(),
    )


def catalog_list_order_by() -> tuple[Any, ...]:
    """Default catalog card order: category (spec) → moment ASC → article nm → code.

    Within one category filter, ``category_spec_order`` is constant so cards
    sort by torque. Across all categories, sidebar order is preserved.
    ``sku_code_nm`` treats digits as numbers when moment is equal/missing;
    ``sku_code`` breaks remaining ties.
    """
    return (
        "category_spec_order",
        "product__category__name",
        F("moment_nm").asc(nulls_last=True),
        F("sku_code_nm").asc(nulls_last=True),
        "sku_code",
    )
