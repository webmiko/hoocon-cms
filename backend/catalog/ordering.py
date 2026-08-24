"""Catalog list ordering helpers (series → Nm/DN → V → control).

SKU ``sku_code`` is lexicographic (``da10…`` before ``da2…``; ``…230…``
before ``…24…``). Cards sort by series family, then numeric moment / DN
(BV/H8205: DN after the ways digit, not the full body code), then voltage
(24 before 230), then ``sku_code`` (control suffix).
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
    """Numeric key from ``sku_code`` (DA/SA torque, BV/LAV DN, else trail).

    Ball-valve / kit bodies encode ``BV{ways}{dn}`` (``215`` → DN15,
    ``2100`` → DN100) — sort by DN, not the full body integer. Same for
    H8205 ``LAV{ways}{dn}``. Examples: ``DA10FU24-D`` → 10,
    ``8100-bv215a`` → 15, ``8100q-bv2100`` → 100, ``H8102-BV265-24A`` → 65,
    ``H8205-LAV232-24A`` → 32 (not voltage 24 from the trail).

    Postgres ``REGEXP_REPLACE`` returns the whole string when the pattern does
    not match; ``NullIf(..., sku_code)`` drops those misses. Use flag ``i``
    (ARE); do not embed ``(?i)`` — that breaks POSIX mode.
    """
    da_sa_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^(da|sa)([0-9]+).*$"),
        Value(r"\2"),
        Value("i"),
    )
    # Brass 8100 / 8100Q / H81: DN after ways digit (2|3).
    bv_dn_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^.*?bv[23]([0-9]+).*$"),
        Value(r"\1"),
        Value("i"),
    )
    # H8205-LAV{2|3}{dn}{opts}-{V}{ctrl} — DN after ways digit, before opts.
    h8205_dn_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^h8205-lav[23]([0-9]+).*$"),
        Value(r"\1"),
        Value("i"),
    )
    trail_or_raw = _RegexpReplace(
        F("sku_code"),
        Value(r"^.*-([0-9]+)[a-z]*$"),
        Value(r"\1"),
        Value("i"),
    )
    picked = Coalesce(
        NullIf(da_sa_or_raw, F("sku_code")),
        NullIf(bv_dn_or_raw, F("sku_code")),
        NullIf(h8205_dn_or_raw, F("sku_code")),
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


def dn_nm_subquery() -> Subquery:
    """Numeric DN from AttributeValue (NULL if missing)."""
    from catalog.models import AttributeValue

    return Subquery(
        AttributeValue.objects.filter(sku_id=OuterRef("pk"))
        .filter(
            Q(attribute__slug="dn") | Q(attribute__name__iexact="dn") | Q(attribute__name__iexact="DN"),
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
    and within a mixed category series stay contiguous. ``8100q`` before
    bare ``8100`` in the Case so flanged stays its own family after brass.
    """
    return Case(
        When(sku_code__iregex=r"(?i)^da\d+mqu", then=Value(20)),
        When(sku_code__iregex=r"(?i)^da\d+mu", then=Value(10)),
        When(sku_code__iregex=r"(?i)^hva", then=Value(30)),
        When(sku_code__iregex=r"(?i)^hvd", then=Value(40)),
        When(sku_code__iregex=r"(?i)^da\d+fu", then=Value(50)),
        When(sku_code__iregex=r"(?i)^sa\d+fu", then=Value(60)),
        When(sku_code__iregex=r"(?i)^sa\d+mu", then=Value(70)),
        When(sku_code__iregex=r"(?i)^8100q-bv", then=Value(85)),
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


def ways_ord_case() -> Case:
    """2-way before 3-way at the same DN (H8205 LAV / brass BV / H81)."""
    return Case(
        When(sku_code__iregex=r"(?i)^h8205-lav2", then=Value(2)),
        When(sku_code__iregex=r"(?i)^h8205-lav3", then=Value(3)),
        When(sku_code__iregex=r"(?i)(?:^|-)bv2[0-9]", then=Value(2)),
        When(sku_code__iregex=r"(?i)(?:^|-)bv3[0-9]", then=Value(3)),
        default=Value(0),
        output_field=IntegerField(),
    )


def annotate_moment_nm(queryset: QuerySet[Any]) -> QuerySet[Any]:
    """Annotate sort keys: series, moment, DN, sku digits, ways, voltage."""
    return queryset.annotate(
        series_ord=series_ord_case(),
        moment_nm=moment_nm_subquery(),
        dn_nm=dn_nm_subquery(),
        sku_code_nm=_parse_sku_code_nm_expr(),
        ways_ord=ways_ord_case(),
        voltage_ord=voltage_ord_case(),
    )


def catalog_list_order_by() -> tuple[Any, ...]:
    """Catalog card order: category → series → Nm/DN → ways → V → sku_code.

    Within one category, series families stay contiguous (DAMU then HVA…,
    then 8100 / 8100Q / H81 / H8205), each by torque or DN (numeric, not
    text), then ways (2 before 3), then 24 V before 230 V; ``sku_code``
    orders control suffixes (A/AS/D/DS/DST/M) and ties.
    """
    return (
        "category_spec_order",
        "product__category__name",
        "series_ord",
        F("moment_nm").asc(nulls_last=True),
        F("dn_nm").asc(nulls_last=True),
        F("sku_code_nm").asc(nulls_last=True),
        "ways_ord",
        "voltage_ord",
        "sku_code",
    )
