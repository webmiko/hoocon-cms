"""Canonical ТТХ facets for catalog filters and card highlights.

Tilda ETL creates duplicate Attribute rows with opaque ``attr-<id>`` slugs.
Public API exposes stable facet keys (``moment``, ``voltage``, …) that match
by Attribute.name patterns (and optional legacy slugs).

Spec: docs/plan-detail-mvp.md S2; docs/market-analysis.md B2.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from django.db.models import QuerySet

from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@dataclass(frozen=True, slots=True)
class FacetDef:
    """One public filter facet."""

    key: str
    label: str
    name_substrings: tuple[str, ...]
    legacy_slugs: tuple[str, ...] = ()
    # Extra: Attribute.name "Мощность" often stores Нм (Tilda mislabel).
    include_power_as_moment: bool = False


# Order = highlight priority on catalog cards / PDP hero.
FACET_DEFS: tuple[FacetDef, ...] = (
    FacetDef(
        key="moment",
        label="Крутящий момент",
        name_substrings=("крутящий момент", "момент"),
        legacy_slugs=("moment",),
        include_power_as_moment=True,
    ),
    FacetDef(
        key="voltage",
        label="Напряжение",
        name_substrings=("напряжение",),
    ),
    FacetDef(
        key="control",
        label="Управление",
        name_substrings=("управление",),
        legacy_slugs=("control",),
    ),
    FacetDef(
        key="area",
        label="Площадь заслонки",
        name_substrings=("площадь",),
        legacy_slugs=("2",),  # historical slug from ETL for area
    ),
    FacetDef(
        key="aux_switch",
        label="Вспомогательный переключатель",
        name_substrings=("вспомогательн",),
    ),
    FacetDef(
        key="dn",
        label="DN",
        name_substrings=("dn",),
        legacy_slugs=("dn",),
    ),
    FacetDef(
        key="ways",
        label="Вид крана",
        name_substrings=("вид крана",),
    ),
    FacetDef(
        key="kvs",
        label="Kvs (м³/ч)",
        name_substrings=("kvs",),
        legacy_slugs=("kvs",),
    ),
    # Belimo codes: card «Аналоги» text, SKU.analog_belimo_code, or ТТХ inference.
    FacetDef(
        key="analog",
        label="Аналоги",
        name_substrings=(),
        legacy_slugs=("analog_belimo_code",),
    ),
)

FACET_BY_KEY: dict[str, FacetDef] = {f.key: f for f in FACET_DEFS}
FACET_KEYS: frozenset[str] = frozenset(FACET_BY_KEY)

# Extra PDP/card rows (not catalog filters): after primary facets.
EXTRA_HIGHLIGHT_DEFS: tuple[FacetDef, ...] = (
    FacetDef(
        key="control_signal",
        label="Управляющий сигнал Y",
        name_substrings=("управляющий сигнал", "сигнал управления"),
        legacy_slugs=("control-signal",),
    ),
    FacetDef(
        key="feedback_signal",
        label="Обратная связь U",
        name_substrings=("обратная связь", "сигнал обратной связи"),
        legacy_slugs=("feedback-signal",),
    ),
    FacetDef(
        key="runtime",
        label="Время поворота",
        name_substrings=("время поворота", "время срабатывания"),
    ),
    FacetDef(
        key="dimensions",
        label="Габаритные размеры",
        name_substrings=("габарит",),
    ),
    FacetDef(
        key="weight",
        label="Масса",
        name_substrings=("масса", "вес"),
    ),
    FacetDef(
        key="ip",
        label="Степень защиты корпуса",
        name_substrings=("степень защиты",),
        legacy_slugs=("ip-rating",),
    ),
    FacetDef(
        key="compatible-actuators",
        label="Совместимый привод",
        name_substrings=("совместимый привод",),
        legacy_slugs=("compatible-actuators",),
    ),
    FacetDef(
        key="bracket",
        label="Кронштейн",
        name_substrings=("кронштейн",),
        legacy_slugs=("bracket",),
    ),
)


def attribute_matches_facet(attr: Attribute, facet: FacetDef) -> bool:
    """Return True if Attribute belongs to the facet definition."""
    if facet.key == "analog":
        # Codes live on SKU.analog_belimo_code, not AttributeValue.
        return False
    slug = attr.slug or ""
    if slug in facet.legacy_slugs:
        return True
    # Tilda used ``kvs-3`` etc. for ball-valve flow coefficients.
    if facet.key == "kvs" and slug.casefold().startswith("kvs"):
        return True
    name = (attr.name or "").casefold()
    if facet.include_power_as_moment and "мощность" in name:
        return True
    # «Управление» facet must not pick manual override / Y-signal rows.
    if facet.key == "control":
        if slug in {"manual-override", "control-signal", "feedback-signal"}:
            return False
        if "ручн" in name or "сигнал" in name or "обратная связь" in name:
            return False
        return name == "управление" or name.startswith("управление ")
    if facet.key == "control_signal":
        if slug == "feedback-signal" or "обратная связь" in name:
            return False
    if facet.key == "feedback_signal":
        if slug == "control-signal" or ("управляющ" in name and "обратн" not in name):
            return False
    # Nominal voltage only — not «Диапазон напряжения».
    if facet.key == "voltage":
        if slug == "voltage-range" or "диапазон" in name:
            return False
    if not facet.name_substrings:
        return False
    return any(token in name for token in facet.name_substrings)


def attribute_ids_for_facet(facet: FacetDef) -> list[int]:
    """Resolve Attribute PKs that feed a facet (cached per request via caller)."""
    ids: list[int] = []
    for attr in Attribute.objects.all().only("id", "name", "slug"):
        if attribute_matches_facet(attr, facet):
            # For mislabeled «Мощность»: only if some values look like torque.
            if facet.include_power_as_moment and "мощность" in (attr.name or "").casefold():
                if not AttributeValue.objects.filter(
                    attribute=attr,
                    value__icontains="Нм",
                ).exists():
                    continue
            ids.append(attr.id)
    return ids


# Marketing notes in Tilda EAV, e.g. «0,3 м² (для огнезадерживающих клапанов НО)».
_FACET_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*")
_AREA_VALUE_RE = re.compile(
    r"^(до\s+)?(\d+(?:[.,]\d+)?)\s*(?:м²|m²|м2|m2)?\s*$",
    re.IGNORECASE,
)


def strip_facet_parenthetical(value: str) -> str:
    """Drop parenthetical marketing notes from a facet value."""
    cleaned = _FACET_PARENTHETICAL_RE.sub(" ", value)
    return " ".join(cleaned.split())


def normalize_area_attribute_value(value: str) -> str:
    """Canonical damper-area label: always ``до N м²``.

    Exact Tilda values (``0,5 м²``) and ``до 0,5`` collapse to the same
    chip so the facet stays uniform.

    Examples:
        ``до 0,5`` → ``до 0,5 м²``;
        ``0,5 м²`` → ``до 0,5 м²``;
        ``3, 2 м²`` → ``до 3,2 м²``.

    Args:
        value: Raw EAV / facet value.

    Returns:
        Normalized area string with ``до`` and ``м²``.
    """
    raw = strip_facet_parenthetical(" ".join(str(value).strip().split()))
    if not raw:
        return raw
    # Tilda typo: «3, 2 м²» → «3,2 м²».
    raw = re.sub(r"(\d),\s+(\d)", r"\1,\2", raw)
    match = _AREA_VALUE_RE.match(raw)
    if not match:
        # Keep unknown forms but unify unit spelling; still prefer «до».
        cleaned = raw.replace("m²", "м²").replace("м2", "м²").replace("m2", "м²")
        if cleaned.casefold().startswith("до "):
            return cleaned
        return f"до {cleaned}"
    number = match.group(2).replace(".", ",")
    return f"до {number} м²"


def _looks_like_area_value(value: str) -> bool:
    """True if text looks like a damper-area facet value."""
    raw = strip_facet_parenthetical(" ".join((value or "").split()))
    if not raw:
        return False
    raw = re.sub(r"(\d),\s+(\d)", r"\1,\2", raw)
    if _AREA_VALUE_RE.match(raw):
        return True
    return bool(re.search(r"м²|m²|м2|m2", raw, re.I))


def normalize_facet_value(
    facet_key: str,
    value: str,
    *,
    sku_code: str | None = None,
    description: str | None = None,
    category_slug: str | None = None,
) -> str:
    """Canonical chip label for aggregation.

    Area / voltage / aux / control collapse to canons.
    """
    val = " ".join(str(value).strip().split())
    if not val:
        return val
    if facet_key == "area":
        return normalize_area_attribute_value(val)
    if facet_key == "voltage":
        from catalog.etl.tech_copy import normalize_voltage_attribute_value

        return normalize_voltage_attribute_value(val, sku_code=sku_code)
    if facet_key == "control":
        from catalog.etl.tech_copy import normalize_control_attribute_value

        return normalize_control_attribute_value(
            val,
            sku_code=sku_code,
            category_slug=category_slug,
        )
    if facet_key == "aux_switch":
        return normalize_aux_switch_value(
            val,
            sku_code=sku_code,
            description=description or "",
        )
    return val


def values_match(stored: str, requested: str) -> bool:
    """Loose equality for facet values (``10`` ≈ ``10 Нм``)."""
    a = " ".join(stored.strip().casefold().split())
    b = " ".join(requested.strip().casefold().split())
    if not a or not b:
        return False
    # Area: «до 0,5» ≈ «до 0,5 м²»; strip parenthetical notes.
    if _looks_like_area_value(stored) or _looks_like_area_value(requested):
        if normalize_area_attribute_value(stored) == normalize_area_attribute_value(
            requested,
        ):
            return True
    if a == b:
        return True
    # Voltage: all Tilda spellings → same Belimo family.
    from catalog.etl.tech_copy import (
        detect_voltage_family,
        normalize_voltage_attribute_value,
    )

    if normalize_voltage_attribute_value(stored) == normalize_voltage_attribute_value(
        requested,
    ):
        # Only treat as voltage match when at least one side looks like voltage.
        if detect_voltage_family(stored) or detect_voltage_family(requested):
            return True
    # Aux: Да/Нет/1 SPDT ↔ Нет / SPDT-1 / SPDT-2 (without SKU context).
    if _looks_like_aux_value(stored) or _looks_like_aux_value(requested):
        if normalize_aux_switch_value(stored) == normalize_aux_switch_value(requested):
            return True
    # Control: legacy «Пропорциональное (модулирующее)» ↔ «Пропорциональное».
    from catalog.etl.tech_copy import normalize_control_attribute_value

    if normalize_control_attribute_value(stored) == normalize_control_attribute_value(
        requested,
    ):
        low_join = f"{a} {b}"
        if re.search(r"управл|позицион|пропорциональн|открыто|модулир|плавн", low_join):
            return True
    # Numeric core: "10" matches "10 Нм", "24" matches "24 В"
    a_num = a.split()[0].replace(",", ".")
    b_num = b.split()[0].replace(",", ".")
    if a_num == b_num and a_num.replace(".", "", 1).isdigit():
        return True
    return a.startswith(b) or b.startswith(a)


def filter_skus_by_facet(
    queryset: QuerySet[SKU],
    facet: FacetDef,
    value: str,
    *,
    attr_ids: Iterable[int] | None = None,
) -> QuerySet[SKU]:
    """Filter SKUs whose EAV value matches the facet (loose)."""
    if facet.key == "analog":
        return _filter_skus_by_belimo_analog(queryset, value)

    ids = list(attr_ids) if attr_ids is not None else attribute_ids_for_facet(facet)
    if not ids:
        return queryset.none()

    # Prefer exact DB filter when possible; fall back to Python match for loose.
    # Area / voltage / control / aux need canon match (legacy spellings in DB).
    if facet.key not in {"aux_switch", "voltage", "control", "area"}:
        exact = queryset.filter(
            attribute_values__attribute_id__in=ids,
            attribute_values__value=value,
        )
        if exact.exists():
            return exact.distinct()

    matching_sku_ids: set[int] = set()
    if facet.key in {"aux_switch", "voltage", "control", "area"}:
        detailed_rows = AttributeValue.objects.filter(
            attribute_id__in=ids,
        ).values_list(
            "sku_id",
            "value",
            "sku__sku_code",
            "sku__description",
            "sku__product__category__slug",
        )
        for sku_id, stored, sku_code, description, category_slug in detailed_rows:
            normalized = normalize_facet_value(
                facet.key,
                str(stored),
                sku_code=str(sku_code or "") or None,
                description=str(description or ""),
                category_slug=str(category_slug or "") or None,
            )
            if normalized == normalize_facet_value(facet.key, value):
                matching_sku_ids.add(sku_id)
            elif values_match(str(stored), value):
                matching_sku_ids.add(sku_id)
    else:
        simple_rows = AttributeValue.objects.filter(
            attribute_id__in=ids,
        ).values_list(
            "sku_id",
            "value",
        )
        for sku_id, stored in simple_rows:
            if values_match(str(stored), value):
                matching_sku_ids.add(sku_id)
    if not matching_sku_ids:
        return queryset.none()
    return queryset.filter(pk__in=matching_sku_ids)


def collect_facet_options(
    *,
    base_queryset: QuerySet[SKU] | None = None,
) -> list[dict[str, object]]:
    """Build facet payload for the public facets endpoint.

    Args:
        base_queryset: Optional SKU scope (e.g. current category). Defaults to
            all published SKUs.

    Returns:
        List of ``{key, label, values: [{value, count}]}``.
    """
    if base_queryset is None:
        base_queryset = SKU.objects.filter(is_published=True)
    sku_ids = list(base_queryset.values_list("id", flat=True))
    result: list[dict[str, object]] = []

    for facet in FACET_DEFS:
        if facet.key == "analog":
            analog_facet = _collect_analog_facet_options(sku_ids)
            if analog_facet is not None:
                result.append(analog_facet)
            continue
        attr_ids = attribute_ids_for_facet(facet)
        if not attr_ids:
            continue
        counts: dict[str, set[int]] = {}
        rows = AttributeValue.objects.filter(
            attribute_id__in=attr_ids,
            sku_id__in=sku_ids,
        ).values_list(
            "sku_id",
            "value",
            "sku__sku_code",
            "sku__description",
            "sku__product__category__slug",
        )
        for sku_id, raw, sku_code, description, category_slug in rows:
            val = normalize_facet_value(
                facet.key,
                str(raw),
                sku_code=str(sku_code or "") or None,
                description=str(description or ""),
                category_slug=str(category_slug or "") or None,
            )
            if not val:
                continue
            # Aux absent («Нет») is not a filter chip — only SPDT-1 / SPDT-2.
            if facet.key == "aux_switch" and val == AUX_SWITCH_NONE:
                continue
            counts.setdefault(val, set()).add(sku_id)
        if not counts:
            continue
        values = [
            {"value": value, "count": len(sku_set)}
            for value, sku_set in sorted(
                counts.items(),
                key=lambda item: _facet_sort_key(facet.key, item[0]),
            )
        ]
        result.append({"key": facet.key, "label": facet.label, "values": values})
    return result


def _filter_skus_by_belimo_analog(
    queryset: QuerySet[SKU],
    value: str,
) -> QuerySet[SKU]:
    """Match SKUs that list the Belimo article (card text, field, or inference)."""
    from catalog.etl.belimo_analogs import belimo_codes_for_sku, normalize_belimo_code

    needle = normalize_belimo_code(value)
    if not needle:
        return queryset.none()
    # Fast path: persisted primary code.
    direct_ids = set(
        queryset.filter(analog_belimo_code__iexact=needle).values_list("id", flat=True),
    )
    skus = queryset.select_related("product", "product__category").prefetch_related(
        "attribute_values__attribute",
    )
    matching: set[int] = set(direct_ids)
    for sku in skus:
        if sku.id in matching:
            continue
        codes = {normalize_belimo_code(c) for c in belimo_codes_for_sku(sku)}
        if needle in codes:
            matching.add(sku.id)
    if not matching:
        return queryset.none()
    return queryset.filter(id__in=matching)


def _collect_analog_facet_options(
    sku_ids: list[int],
) -> dict[str, object] | None:
    """Build «Аналоги» facet from card Belimo lines, field, or ТТХ inference."""
    from catalog.etl.belimo_analogs import belimo_codes_for_sku

    if not sku_ids:
        return None
    counts: dict[str, set[int]] = {}
    skus = (
        SKU.objects.filter(id__in=sku_ids)
        .select_related("product", "product__category")
        .prefetch_related("attribute_values__attribute")
    )
    for sku in skus:
        for code in belimo_codes_for_sku(sku):
            counts.setdefault(code, set()).add(sku.id)
    if not counts:
        return None
    values = [
        {"value": value, "count": len(sku_set)}
        for value, sku_set in sorted(
            counts.items(),
            key=lambda item: _facet_sort_key("analog", item[0]),
        )
    ]
    return {
        "key": "analog",
        "label": FACET_BY_KEY["analog"].label,
        "values": values,
    }


def _facet_sort_key(facet_key: str, value: str) -> tuple:
    """Sort numeric-ish facets by number, else alphabetically."""
    if facet_key == "aux_switch":
        order = {"нет": 0, "spdt-1": 1, "spdt-2": 2}
        return (order.get(value.casefold(), 9), value.casefold())
    if facet_key == "control":
        order = {
            "открыто/закрыто": 0,
            "2-/3-позиционное": 1,
            "пропорциональное": 2,
        }
        return (order.get(value.casefold(), 9), value.casefold())
    if facet_key == "area":
        match = re.search(r"(\d+[.,]?\d*)", value)
        number = float(match.group(1).replace(",", ".")) if match else 0.0
        return (number,)
    if facet_key in {"moment", "voltage", "dn", "kvs"}:
        token = value.split()[0].replace(",", ".").replace("до", "").strip()
        try:
            return (0, float(token))
        except ValueError:
            return (1, value.casefold())
    return (0, value.casefold())


AUX_SWITCH_NONE = "Нет"
AUX_SWITCH_SPDT_1 = "SPDT-1"
AUX_SWITCH_SPDT_2 = "SPDT-2"

_AUX_ABSENT = frozenset({"нет", "no", "false", "0", "-", "без", "отсутствует"})
_AUX_PRESENT = frozenset({"да", "yes", "true", "1", "есть"})


def _looks_like_aux_value(value: str) -> bool:
    """True if text is a boolean / SPDT aux-switch label."""
    low = " ".join((value or "").casefold().split())
    if not low:
        return False
    if low in _AUX_ABSENT or low in _AUX_PRESENT:
        return True
    return bool(re.search(r"spdt", low, re.I))


def aux_spdt_count_from_sku(sku_code: str) -> int | None:
    """Infer SPDT count from edition suffix (Belimo DS=1, AS/S=2).

    Args:
        sku_code: Edition code, e.g. ``da5fu24-ds``, ``HVA24S-5``.

    Returns:
        ``0`` (none), ``1``, ``2``, or ``None`` if unknown.
    """
    code = (sku_code or "").strip().lower().replace(" ", "")
    if not code:
        return None
    if re.search(r"-as(?:$|[^a-z])", code) or code.endswith("-as"):
        return 2
    if re.search(r"-dst(?:$|[^a-z])", code) or code.endswith("-dst"):
        return 1
    if re.search(r"-ds(?:$|[^a-z])", code) or code.endswith("-ds"):
        return 1
    # HVA24S-5 / HVD230S-10 — «S» edition = 2 auxiliary switches.
    if re.search(r"(?:hva|hvd)\d*s-?\d", code):
        return 2
    if re.search(r"-a(?:$|[^a-z])", code) or code.endswith("-a"):
        return 0
    if re.search(r"-d(?:$|[^a-z])", code) or code.endswith("-d"):
        return 0
    return None


def normalize_aux_switch_value(
    value: str,
    *,
    sku_code: str | None = None,
    description: str = "",
) -> str:
    """Canonical aux facet / ТТХ: ``Нет`` / ``SPDT-1`` / ``SPDT-2``.

    Args:
        value: Raw EAV (Да / Нет / ``2 SPDT`` / ``SPDT-2``).
        sku_code: Edition code for DS/AS/S count and to fix mislabeled Да.
        description: SKU text that may mention ``1 SPDT`` / ``2 SPDT``.

    Returns:
        One of the three canonical labels.
    """
    raw = " ".join((value or "").split())
    low = raw.casefold()

    def _label(count: int) -> str:
        if count <= 0:
            return AUX_SWITCH_NONE
        if count == 1:
            return AUX_SWITCH_SPDT_1
        return AUX_SWITCH_SPDT_2

    # Edition suffix is authoritative (series texts often say «2 SPDT» for all).
    sku_count = aux_spdt_count_from_sku(sku_code or "")
    if sku_count is not None:
        return _label(sku_count)

    count_match = re.search(r"(?:spdt\s*[-–—]?\s*(\d)|(\d)\s*[-–—]?\s*spdt)", raw, re.I)
    if count_match:
        digit = count_match.group(1) or count_match.group(2)
        return _label(int(digit))

    if low in _AUX_ABSENT:
        return AUX_SWITCH_NONE

    desc_match = re.search(
        r"(?:spdt\s*[-–—]?\s*(\d)|(\d)\s*[-–—]?\s*spdt)",
        description or "",
        re.I,
    )
    if desc_match:
        digit = desc_match.group(1) or desc_match.group(2)
        return _label(int(digit))

    if low in _AUX_PRESENT or "spdt" in low:
        # Legacy «Да» without SKU context — Belimo AS default is two switches.
        return AUX_SWITCH_SPDT_2

    if len(raw) <= 24 and raw:
        return raw
    return AUX_SWITCH_NONE


def format_aux_switch_display(
    value: str,
    *,
    description: str = "",
    sku_code: str | None = None,
) -> str | None:
    """Format auxiliary-switch value for hero / cards.

    - Absent / «Нет» → ``None`` (do not show on cards).
    - Present → ``SPDT-1`` or ``SPDT-2``.

    Args:
        value: Raw AttributeValue (Да / Нет / already ``SPDT-2``).
        description: Optional SKU text to detect switch count.
        sku_code: Edition code (DS=1, AS/S=2).

    Returns:
        Display string or None to hide the row.
    """
    normalized = normalize_aux_switch_value(
        value,
        sku_code=sku_code,
        description=description,
    )
    if normalized == AUX_SWITCH_NONE:
        return None
    if normalized in {AUX_SWITCH_SPDT_1, AUX_SWITCH_SPDT_2}:
        return normalized
    return None


_HEADING_AUX_ABSENT = re.compile(
    r"\s*[-–—]\s*(?:нет|no|без|отсутствует)\s*$",
    re.IGNORECASE,
)
_HEADING_AUX_PRESENT = re.compile(
    r"\s*[-–—]\s*(?:да|yes|есть)\s*$",
    re.IGNORECASE,
)
# Store CSV: ``SERIES | 8Нм Product name - 8 Нм - 230 В - Control - Нет``
_HEADING_PIPE = re.compile(
    r"^(?P<code>[^|]+)\|\s*"
    r"(?:(?P<nm>[\d.,]+)\s*нм\s+)?"
    r"(?P<body>.+)$",
    re.IGNORECASE,
)
_HEADING_EDITION_TRAILER = re.compile(
    r"\s*[-–—]\s+\d+[.,]?\d*\s*нм\b.*$",
    re.IGNORECASE,
)
# Store CSV valve trailer: ``- 2-ходовый - 15 - 1,6`` (ways / DN / Kvs).
_HEADING_VALVE_TRAILER = re.compile(
    r"\s*[-–—]\s*\d+-ходов\w*\s*[-–—]\s*\d+\s*[-–—]\s*[\d.,]+\s*$",
    re.IGNORECASE,
)
# Control-type phrases baked into the body before the edition trailer
# (HVA/HVD series): «пропорциональное управление», «управление 2-/3-позиционное»,
# «позиционное управление», «Плавное управление», «Открыто/Закрыто».
# Stripped from the end of the body; control type belongs in highlights.
_HEADING_CONTROL_TAIL = re.compile(
    r"\s+"
    r"(?:"
    r"(?:пропорциональн\w*|плавн\w*|позицион\w*)\s+управление"
    r"|управление\s+(?:2-?/?3?-?позицион\w*|позицион\w*)"
    r"|2-?/?3?-?позицион\w*"
    r"|открыт\w*/?\s*закрыт\w*"
    r")"
    r"\s*$",
    re.IGNORECASE,
)
# Canonical word order for fast-acting springless actuators: «ускоренного
# срабатывания без возвратной пружины» (matches DA8MQU canon). HVA-5Q raw
# stores the reverse order; swap so the family reads the same across series.
_HEADING_REORDER_FAST = re.compile(
    r"\bбез\s+возвратной\s+пружины\s+ускоренного\s+срабатывания\b",
    re.IGNORECASE,
)
# Bare product noun → SEO-valuable «Электропривод» (matches category names
# «Электроприводы …»). Only matches a standalone lead word so mid-body
# occurrences (none currently) are untouched.
_HEADING_PRIVOD_TO_ELEKTRO = re.compile(r"^привод\b", re.IGNORECASE)
_LEAD_SKIP = re.compile(
    r"^(?:[-–—•*]|\d+[.)])\s*|"
    r"^(?:номинальн|управлен|питание|сигнал|основные|характеристик)",
    re.IGNORECASE,
)


def _norm_heading_phrase(text: str) -> str:
    """Normalize a phrase for heading/description echo comparison."""
    s = " ".join((text or "").casefold().split())
    if "|" in s:
        s = s.split("|", 1)[-1].strip()
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def _heading_article(sku_code: str, fallback: str) -> str:
    """Unique left-side article for H1 / cards.

    Ball valves: ``8100-bv215a`` → ``BV215A``. Actuators: keep ``sku_code``.
    """
    code = (sku_code or "").strip()
    if not code:
        return fallback
    m = re.match(r"(?i)^8100-(.+)$", code)
    if m:
        return m.group(1).upper()
    return code


def _strip_control_tail(body: str) -> str:
    """Drop a trailing control-type phrase baked into the heading body.

    HVA/HVD raw names embed «пропорциональное управление» / «управление
    2-/3-позиционное» / «позиционное управление» before the edition trailer.
    Control type belongs in highlights, not H1 — but restore the original
    body when stripping would leave a bare product noun («Привод …» →
    «Привод»), which is too generic for a unique title.

    Args:
        body: Body text after pipe split and edition/valve trailer strip.

    Returns:
        Body without the trailing control phrase, or the original body when
        the result would be too short.
    """
    if not body:
        return body
    stripped = _HEADING_CONTROL_TAIL.sub("", body).strip(" |-–—")
    if not stripped or len(stripped.split()) < 2:
        return body
    return stripped


def format_sku_heading_name(
    name: str,
    *,
    description: str = "",
    sku_code: str = "",
    kvs: str = "",
) -> str:
    """Clean store CSV title for H1 / cards: unique article + product type.

    Strips edition trailer (``- 8 Нм - 230 В - управление - Нет/Да``),
    valve facet trailer (``- 2-ходовый - 15 - 1,6``), optional ``NНм`` after
    ``|``, and control-type phrases baked into the body (``пропорциональное
    управление``, ``управление 2-/3-позиционное``). Normalizes the bare
    product noun to SEO-valuable «Электропривод» and unifies the word order
    for fast-acting springless actuators. When ``sku_code`` is set, the left
    side is the article (unique per SKU). Ball valves append ``Kvs`` when
    provided.

    Args:
        name: Raw ``SKU.name`` from import.
        description: Unused; kept for call-site compatibility.
        sku_code: SKU article for unique heading prefix.
        kvs: Optional Kvs value for valve titles.

    Returns:
        Display title, e.g. ``DA8MU24-D | Электропривод воздушный…`` or
        ``BV215A | Шаровой кран 2-ходовый DN 15, Kvs 1,6``.
    """
    _ = description  # call-site compat; aux lives in highlights
    from catalog.etl.tech_copy import normalize_tech_copy

    text = normalize_tech_copy(" ".join((name or "").split()))
    if not text:
        return (sku_code or "").strip()

    # Product titles: «пропорциональное управление» without Belimo parenthetical.
    text = re.sub(
        r"\s*\(\s*модулирующ\w*\s*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = " ".join(text.split())

    if _HEADING_AUX_ABSENT.search(text):
        text = _HEADING_AUX_ABSENT.sub("", text).rstrip(" -–—")
    if _HEADING_AUX_PRESENT.search(text):
        text = _HEADING_AUX_PRESENT.sub("", text).rstrip(" -–—")

    code = ""
    body = text
    pipe = _HEADING_PIPE.match(text)
    if pipe:
        code = pipe.group("code").strip()
        body = pipe.group("body").strip()
        body = _HEADING_EDITION_TRAILER.sub("", body).strip()
        body = _HEADING_VALVE_TRAILER.sub("", body).strip()
        body = re.sub(
            r"\s*[-–—]\s*(?:пропорциональн\w*.*|2-/3-позицион\w*|открыто.*)$",
            "",
            body,
            flags=re.IGNORECASE,
        ).strip()
        body = _strip_control_tail(body)
    else:
        body = _HEADING_EDITION_TRAILER.sub("", text).strip()
        body = _HEADING_VALVE_TRAILER.sub("", body).strip()
        body = _strip_control_tail(body)

    article = _heading_article(sku_code, code)
    # Drop accidental article echo inside body.
    if article and body:
        body = re.sub(
            re.escape(article),
            "",
            body,
            flags=re.IGNORECASE,
        ).strip(" |-–—")

    # Torque belongs in highlights — never echo «N Нм» in the display title.
    body = re.sub(
        r"(?:^|\s)\d+[.,]?\d*\s*нм\b",
        "",
        body,
        flags=re.IGNORECASE,
    )
    body = _HEADING_REORDER_FAST.sub(
        "ускоренного срабатывания без возвратной пружины",
        body,
    )
    body = _HEADING_PRIVOD_TO_ELEKTRO.sub("Электропривод", body, count=1)
    body = " ".join(body.split()).strip(" |-–—")

    kvs_val = " ".join((kvs or "").split())
    if kvs_val and body and "kvs" not in body.casefold():
        body = f"{body}, Kvs {kvs_val}"

    if article and body:
        return f"{article} | {body}"
    return article or body


def extract_sku_lead(description: str, *, max_len: int = 220) -> str:
    """Pick the first prose sentence(s) from a structured description.

    Skips bullet lists and section headers (``Управление:``). Prefer the
    application blurb, e.g. «Электропривод воздушный… Используется в…».

    Args:
        description: SKU / product description text.
        max_len: Soft cap for hero lead.

    Returns:
        Plain lead text or empty string.
    """
    from catalog.etl.tech_copy import normalize_tech_copy

    if not description or not description.strip():
        return ""
    text = normalize_tech_copy(description.replace("\xa0", " "))
    candidates: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or len(line) < 40:
            continue
        if _LEAD_SKIP.search(line):
            continue
        if line.endswith(":"):
            continue
        candidates.append(line)
    if not candidates:
        return ""
    # Prefer the longest prose block (usually the product blurb).
    lead = max(candidates, key=len)
    # If the blurb is «Name. Application…», keep only the application sentence.
    parts = re.split(r"(?<=[.!?…])\s+", lead)
    if len(parts) >= 2:
        for part in parts[1:]:
            if re.match(
                r"(?i)^(?:используется|применяется|предназначен|для\b)",
                part,
            ):
                lead = part
                break
        else:
            # Drop the first sentence when it is a product-type restatement.
            if len(parts[0]) < 120 and len(parts[1]) > 20:
                lead = " ".join(parts[1:])
    if len(lead) <= max_len:
        return lead
    cut = lead[: max_len - 1].rsplit(" ", 1)[0]
    return f"{cut}…" if cut else lead[:max_len]


def strip_heading_echo_from_description(
    description: str,
    *,
    heading: str = "",
    lead: str = "",
) -> str:
    """Drop opening sentences that repeat H1 / hero lead.

    Args:
        description: Structured SKU description.
        heading: Formatted H1 (series + product type).
        lead: Hero lead already shown under H1.

    Returns:
        Description without echoed opening prose.
    """
    if not description or not description.strip():
        return ""
    heading_n = _norm_heading_phrase(heading)
    lead_n = _norm_heading_phrase(lead)
    lines = description.replace("\xa0", " ").splitlines()
    out: list[str] = []
    stripped_prose = False
    for raw in lines:
        line = raw.rstrip()
        stripped = " ".join(line.split())
        # Skip thin opening one-liners that only restate card ТТХ
        # («привод 10 Нм управления 2-/3-позиционное…»).
        if (
            not stripped_prose
            and stripped
            and not _LEAD_SKIP.search(stripped)
            and re.match(r"(?i)^привод\s+\d+", stripped)
            and len(stripped) < 140
        ):
            continue
        if not stripped_prose and stripped and not _LEAD_SKIP.search(stripped):
            parts = re.split(r"(?<=[.!?…])\s+", stripped)
            kept: list[str] = []
            for part in parts:
                pn = _norm_heading_phrase(part)
                if not pn:
                    continue
                if lead_n and (pn == lead_n or lead_n in pn or pn in lead_n):
                    continue
                if heading_n and (
                    pn == heading_n or heading_n in pn or pn in heading_n or _phrases_echo(heading_n, pn)
                ):
                    continue
                kept.append(part)
            stripped_prose = True
            if kept:
                out.append(" ".join(kept))
            continue
        out.append(line)
    # Drop leading blank lines after strip.
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out).strip()


def _phrases_echo(heading: str, sentence: str) -> bool:
    """True when sentence restates the product-type heading (near-duplicate)."""
    if len(heading) < 24 or len(sentence) < 24:
        return False
    h_tokens = set(heading.split())
    s_tokens = set(sentence.split())
    if len(h_tokens) < 4 or len(s_tokens) < 4:
        return False
    overlap = len(h_tokens & s_tokens) / min(len(h_tokens), len(s_tokens))
    # «электропривод воздушный…» vs «электропривод воздушной заслонки…»
    return overlap >= 0.55 and ("электропривод" in h_tokens or "привод" in h_tokens or "кран" in h_tokens)


_BULLET_ATTR_LINE = re.compile(
    r"^(?:[-–—•*]|\d+[.)])\s*(?P<body>.+)$",
)


def strip_attribute_echo_from_text(
    text: str,
    attributes: Iterable[dict[str, str]],
) -> str:
    """Remove bullet lines that repeat structured AttributeValue rows.

    Keeps section headers and prose that are not covered by EAV. Orphan
    headers (no remaining body) are dropped. Soft-wrapped continuation
    lines after a removed bullet are dropped too.

    Args:
        text: ``specs_text`` or description with bullets.
        attributes: ``[{name, value}]`` (unit optional / ignored).

    Returns:
        Filtered text, possibly empty.
    """
    rows = list(attributes)
    if not text or not text.strip() or not rows:
        return (text or "").strip()

    names: set[str] = set()
    values: set[str] = set()
    for row in rows:
        name_n = _norm_heading_phrase(str(row.get("name") or ""))
        value_n = _norm_heading_phrase(str(row.get("value") or ""))
        if name_n:
            names.add(name_n)
        if value_n:
            values.add(value_n)
            bare = re.sub(r"\s+(нм|мм|кг|м²|с|в|°c|дб.?a?)\s*$", "", value_n)
            if bare and bare != value_n:
                values.add(bare)

    lines = text.replace("\xa0", " ").splitlines()
    kept: list[str] = []
    skip_continuations = False
    for raw in lines:
        stripped = " ".join(raw.split())
        if not stripped:
            kept.append("")
            skip_continuations = False
            continue
        bullet = _BULLET_ATTR_LINE.match(stripped)
        if bullet:
            body = bullet.group("body").strip()
            if _bullet_echoes_attribute(body, names=names, values=values):
                skip_continuations = True
                continue
            skip_continuations = False
            kept.append(raw.rstrip())
            continue
        if skip_continuations and not stripped.endswith(":"):
            continue
        skip_continuations = False
        kept.append(raw.rstrip())

    return _drop_orphan_section_headers(kept)


def _bullet_echoes_attribute(
    body: str,
    *,
    names: set[str],
    values: set[str],
) -> bool:
    """True if a bullet body is already represented as an attribute row."""
    if ":" in body:
        label, _, value = body.partition(":")
        label_n = _norm_heading_phrase(label)
        value_n = _norm_heading_phrase(value)
        if label_n and _label_matches_attr_name(label_n, names):
            return True
        if value_n and value_n in values:
            return True
        if "вспомогательн" in label_n and value_n in {
            "нет",
            "отсутствует",
            "без",
            "no",
        }:
            return True
    body_n = _norm_heading_phrase(body)
    if body_n in values:
        return True
    return False


def _label_matches_attr_name(label_n: str, names: set[str]) -> bool:
    """Match «Площадь обслуживаемой заслонки» to «Площадь заслонки (м²)»."""
    stop = {"м", "мм", "кг", "с", "в", "нм", "до", "макс", "min", "max"}
    qualifiers = frozenset(
        {
            "номинальное",
            "номинальный",
            "рабочее",
            "рабочий",
            "максимальное",
            "максимальный",
        },
    )
    for name_n in names:
        if label_n == name_n:
            return True
        # «номинальное напряжение» ↔ «напряжение»; not «ручное управление».
        if name_n and label_n.endswith(name_n):
            prefix = label_n[: -len(name_n)].strip(" -–—")
            if not prefix or prefix in qualifiers:
                return True
        lt = {t for t in label_n.split() if t not in stop and len(t) > 2}
        nt = {t for t in name_n.split() if t not in stop and len(t) > 2}
        if len(nt) >= 2 and len(lt & nt) >= 2:
            return True
        if len(nt) >= 2 and nt <= lt:
            return True
    return False


def _drop_orphan_section_headers(lines: list[str]) -> str:
    """Drop headers that have no content until the next header / EOF."""
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = " ".join(line.split())
        is_header = bool(stripped) and stripped.endswith(":") and not (_BULLET_ATTR_LINE.match(stripped))
        if is_header:
            j = i + 1
            has_body = False
            while j < len(lines):
                nxt = " ".join(lines[j].split())
                if not nxt:
                    j += 1
                    continue
                if nxt.endswith(":") and not _BULLET_ATTR_LINE.match(nxt):
                    break
                has_body = True
                break
            if not has_body:
                i += 1
                continue
        cleaned.append(line)
        i += 1

    # Collapse excess blank lines.
    out: list[str] = []
    blank = 0
    for line in cleaned:
        if not line.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def highlights_for_sku(
    attribute_values: Iterable[AttributeValue],
    *,
    limit: int = 9,
    description: str = "",
    sku_code: str | None = None,
    category_slug: str | None = None,
) -> list[dict[str, str]]:
    """Pick compact ТТХ rows for catalog cards / PDP hero.

    Args:
        attribute_values: Prefetched AttributeValue rows (with attribute).
        limit: Max rows to return.
        description: SKU description (used to resolve SPDT count).
        sku_code: Edition code for voltage / control / aux canon.
        category_slug: Category slug for control ON/OFF vs floating.

    Returns:
        ``[{key, name, value, unit}]`` in facet priority order (deduped by key).
    """
    values = dedupe_attribute_values(attribute_values)
    by_key: dict[str, dict[str, str]] = {}
    highlight_defs = (*FACET_DEFS, *EXTRA_HIGHLIGHT_DEFS)
    for av in values:
        attr = cast(Attribute, av.attribute)
        for facet in highlight_defs:
            if facet.key in by_key:
                continue
            if not attribute_matches_facet(attr, facet):
                continue
            # Skip mislabeled power unless value looks like torque.
            if (
                facet.include_power_as_moment
                and "мощность" in (attr.name or "").casefold()
                and "нм" not in str(av.value).casefold()
            ):
                continue

            display = str(av.value).strip()
            label = facet.label
            if facet.key == "control":
                from catalog.etl.tech_copy import normalize_control_attribute_value

                display = normalize_control_attribute_value(
                    display,
                    sku_code=sku_code,
                    category_slug=category_slug,
                )
            if facet.key == "area":
                display = normalize_area_attribute_value(display)
            if facet.key == "voltage":
                from catalog.etl.tech_copy import normalize_voltage_attribute_value

                display = normalize_voltage_attribute_value(
                    display,
                    sku_code=sku_code,
                )
            if facet.key == "aux_switch":
                formatted = format_aux_switch_display(
                    display,
                    description=description,
                    sku_code=sku_code,
                )
                if formatted is None:
                    continue
                display = formatted
                label = "Вспом. переключатель"

            if facet.key in {"control_signal", "feedback_signal"}:
                from catalog.etl.tech_copy import (
                    CONTROL_SIGNAL_Y_LABEL,
                    FEEDBACK_SIGNAL_U_LABEL,
                    normalize_modulating_signal_value,
                )

                display = normalize_modulating_signal_value(display)
                label = CONTROL_SIGNAL_Y_LABEL if facet.key == "control_signal" else FEEDBACK_SIGNAL_U_LABEL
            if facet.key == "runtime":
                from catalog.etl.tech_copy import (
                    attribute_display_unit,
                    normalize_running_time_value,
                )

                display = normalize_running_time_value(display)
                unit = attribute_display_unit(display, attr.unit or "")
            elif facet.key == "kvs":
                # Kvs label already includes (м³/ч) — avoid «Kvs (м³/ч): 1,6 м³/ч».
                unit = ""
            else:
                from catalog.etl.tech_copy import attribute_display_unit

                unit = attribute_display_unit(display, attr.unit or "")

            by_key[facet.key] = {
                "key": facet.key,
                "name": label,
                "value": display,
                "unit": unit,
            }
            break
        if len(by_key) >= limit + 2:
            # Allow room for Y/U inject before final trim.
            break

    _ensure_modulating_signal_highlights(by_key)

    ordered: list[dict[str, str]] = []
    seen: set[str] = set()
    for facet in highlight_defs:
        # Inserted immediately after «Управление», not at EXTRA position.
        if facet.key in {"control_signal", "feedback_signal"}:
            continue
        if facet.key in by_key and facet.key not in seen:
            ordered.append(by_key[facet.key])
            seen.add(facet.key)
        if facet.key == "control":
            for signal_key in ("control_signal", "feedback_signal"):
                if signal_key in by_key and signal_key not in seen:
                    ordered.append(by_key[signal_key])
                    seen.add(signal_key)
        if len(ordered) >= limit:
            break
    return ordered


def _ensure_modulating_signal_highlights(
    by_key: dict[str, dict[str, str]],
) -> None:
    """Require Y/U signal rows when control is пропорциональное."""
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        CONTROL_SIGNAL_Y_LABEL,
        FEEDBACK_SIGNAL_U_CANON,
        FEEDBACK_SIGNAL_U_LABEL,
        is_proportional_control,
    )

    control = by_key.get("control", {}).get("value", "")
    if not is_proportional_control(control):
        by_key.pop("control_signal", None)
        by_key.pop("feedback_signal", None)
        return
    if "control_signal" not in by_key:
        by_key["control_signal"] = {
            "key": "control_signal",
            "name": CONTROL_SIGNAL_Y_LABEL,
            "value": CONTROL_SIGNAL_Y_CANON,
            "unit": "",
        }
    if "feedback_signal" not in by_key:
        by_key["feedback_signal"] = {
            "key": "feedback_signal",
            "name": FEEDBACK_SIGNAL_U_LABEL,
            "value": FEEDBACK_SIGNAL_U_CANON,
            "unit": "",
        }


def ensure_modulating_signal_attributes(sku: SKU) -> int:
    """Persist Belimo Y/U signal EAV for пропорциональное editions.

    Args:
        sku: Published or draft SKU with control attribute.

    Returns:
        Number of AttributeValue rows created or updated.
    """
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        CONTROL_SIGNAL_Y_LABEL,
        CONTROL_SIGNAL_Y_SLUG,
        FEEDBACK_SIGNAL_U_CANON,
        FEEDBACK_SIGNAL_U_LABEL,
        FEEDBACK_SIGNAL_U_SLUG,
        is_proportional_control,
        normalize_control_attribute_value,
    )

    control_raw = ""
    for av in sku.attribute_values.select_related("attribute"):
        attr = cast(Attribute, av.attribute)
        if attribute_matches_facet(attr, FACET_BY_KEY["control"]):
            control_raw = str(av.value or "")
            break
    category_slug = ""
    product = cast(Product | None, sku.product) if sku.product_id else None
    if product is not None and product.category_id:
        category = cast(Category, product.category)
        category_slug = category.slug
    control = normalize_control_attribute_value(
        control_raw,
        sku_code=sku.sku_code,
        category_slug=category_slug or None,
    )
    if not is_proportional_control(control):
        return 0

    changed = 0
    specs = (
        (CONTROL_SIGNAL_Y_SLUG, CONTROL_SIGNAL_Y_LABEL, CONTROL_SIGNAL_Y_CANON),
        (FEEDBACK_SIGNAL_U_SLUG, FEEDBACK_SIGNAL_U_LABEL, FEEDBACK_SIGNAL_U_CANON),
    )
    for slug, name, value in specs:
        attr, _created = Attribute.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "unit": ""},
        )
        if attr.name != name:
            attr.name = name
            attr.save(update_fields=["name"])
        av, created = AttributeValue.objects.get_or_create(
            sku=sku,
            attribute=attr,
            defaults={"value": value},
        )
        if created:
            changed += 1
            continue
        if (av.value or "").strip() != value:
            av.value = value
            av.save(update_fields=["value"])
            changed += 1
    return changed


def _normalize_attr_name(name: str) -> str:
    """Collapse Attribute.name variants for duplicate detection."""
    text = " ".join((name or "").casefold().split())
    text = re.sub(r"\([^)]*\)", "", text).strip()
    # Treat mislabeled «Мощность» with torque semantics as moment.
    if text == "мощность":
        return "крутящий момент"
    if text in {"вид", "вид крана"}:
        return "вид"
    return text


def _attr_prefer_score(name: str) -> int:
    """Higher = keep this Attribute row when collapsing duplicates."""
    low = (name or "").casefold()
    score = 0
    if "крутящий момент" in low:
        score += 20
    if "мощность" in low:
        score -= 10
    if "вид крана" in low:
        score += 5
    # Prefer shorter opaque-slug-free readable names slightly by length.
    score -= min(len(low), 40) // 20
    return score


def dedupe_attribute_values(
    attribute_values: Iterable[AttributeValue],
) -> list[AttributeValue]:
    """Drop duplicate ТТХ rows (same name/value from parallel Tilda attrs).

    Keeps the preferred Attribute when names collide (e.g. «Крутящий момент»
    over mislabeled «Мощность» with the same Нм value).

    Args:
        attribute_values: Prefetched rows with ``attribute`` selected.

    Returns:
        Deduplicated list preserving first-seen order of winners.
    """
    best: dict[tuple[str, str], AttributeValue] = {}
    order: list[tuple[str, str]] = []
    for av in attribute_values:
        attr = cast(Attribute, av.attribute) if av.attribute_id else None
        name = attr.name if attr is not None else ""
        value = " ".join(str(av.value).split())
        key = (_normalize_attr_name(name), value.casefold())
        if key not in best:
            best[key] = av
            order.append(key)
            continue
        current = best[key]
        cur_attr = cast(Attribute, current.attribute) if current.attribute_id else None
        cur_name = cur_attr.name if cur_attr is not None else ""
        if _attr_prefer_score(name) > _attr_prefer_score(cur_name):
            best[key] = av
    return [best[key] for key in order]
