"""Catalog list ordering helpers (series → Nm → V → control).

SKU ``sku_code`` is lexicographic (``da10…`` before ``da2…``; ``…230…``
before ``…24…``). Cards sort by series family, then numeric moment / article
digits, then voltage (24 before 230), then ``sku_code`` (control suffix).
"""

from __future__ import annotations

from typing import Any

from django.db.models import (
    Case,
    F,
    FloatField,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
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


def series_ord_case() -> Case:
    """Stable series family rank (DAMU before HVA before HVD, …).

    ``da*mqu`` must be matched before ``da*mu``. H81 / H8205 / brass after
    actuators so «Все категории» keeps drives then valves/kits by category,
    and within a mixed category series stay contiguous.
    """
    return Case(
        When(sku_code__iregex=r"(?i)^da\d+mqu", then=Value(20)),
        When(sku_code__iregex=r"(?i)^da\d+mu", then=Value(10)),
        When(sku_code__iregex=r"(?i)^hva", then=Value(30)),
        When(sku_code__iregex=r"(?i)^hvd", then=Value(40)),
        When(sku_code__iregex=r"(?i)^da\d+fu", then=Value(50)),
        When(sku_code__iregex=r"(?i)^sa\d+fu", then=Value(60)),
        When(sku_code__iregex=r"(?i)^sa\d+mu", then=Value(70)),
        When(sku_code__iregex=r"(?i)^8100-bv", then=Value(80)),
        When(sku_code__iregex=r"(?i)^h81", then=Value(90)),
        When(sku_code__iregex=r"(?i)^h8205", then=Value(100)),
        default=Value(999),
        output_field=IntegerField(),
    )


def voltage_ord_case() -> Case:
    """24 V before 230 V (lexicographic sku_code puts 230 first)."""
    return Case(
        When(sku_code__iregex=r"(?i)230", then=Value(2)),
        When(sku_code__iregex=r"(?i)(?:^|[^0-9])24(?:[^0-9]|$)", then=Value(1)),
        default=Value(99),
        output_field=IntegerField(),
    )


def annotate_moment_nm(queryset: QuerySet[Any]) -> QuerySet[Any]:
    """Annotate sort keys: series, moment, sku digits, voltage."""
    return queryset.annotate(
        series_ord=series_ord_case(),
        moment_nm=moment_nm_subquery(),
        sku_code_nm=_parse_sku_code_nm_expr(),
        voltage_ord=voltage_ord_case(),
    )


def catalog_list_order_by() -> tuple[Any, ...]:
    """Catalog card order: category → series → Nm → V → sku_code (control).

    Within one category, series families stay contiguous (DAMU then HVA…),
    each by torque / DN, then 24 V before 230 V; ``sku_code`` orders control
    suffixes (A/AS/D/DS/DST/M) and remaining ties.
    """
    return (
        "category_spec_order",
        "product__category__name",
        "series_ord",
        F("moment_nm").asc(nulls_last=True),
        F("sku_code_nm").asc(nulls_last=True),
        "voltage_ord",
        "sku_code",
    )
