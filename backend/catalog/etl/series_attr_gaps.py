"""Audit missing ТТХ attrs on DA / SA / HV published SKUs.

Used by ``manage.py audit_series_attr_gaps`` for ETL gap triage (not a write path).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from catalog.models import SKU, AttributeValue

DEFAULT_ATTR_SLUGS: Final[tuple[str, ...]] = (
    "weight",
    "cable-length",
    "wire-cross-section",
)

_FAMILY_ORDER: Final[tuple[str, ...]] = (
    "DAMU",
    "DAFU",
    "DAMQU",
    "SAMU",
    "SAFU",
    "HVA",
    "HVD",
)


def series_family(sku_code: str) -> str | None:
    """Map a SKU code to DA/SA/HV family label, or ``None`` if out of scope."""
    code = (sku_code or "").upper().replace(" ", "")
    if re.match(r"^DA\d+MQU", code):
        return "DAMQU"
    if re.match(r"^DA\d+MU", code):
        return "DAMU"
    if re.match(r"^DA\d+FU", code):
        return "DAFU"
    if re.match(r"^SA\d+MU", code):
        return "SAMU"
    if re.match(r"^SA\d+FU", code):
        return "SAFU"
    if code.startswith("HVA"):
        return "HVA"
    if code.startswith("HVD"):
        return "HVD"
    return None


def series_base_model(sku_code: str, family: str) -> str:
    """Collapse voltage/control editions to one torque-family label."""
    code = (sku_code or "").upper().replace(" ", "")
    if family == "DAMU":
        match = re.match(r"^(DA\d+MU)", code)
        return match.group(1) if match else code
    if family == "DAFU":
        match = re.match(r"^(DA\d+FU)", code)
        return match.group(1) if match else code
    if family == "DAMQU":
        match = re.match(r"^(DA\d+MQU)", code)
        return match.group(1) if match else code
    if family == "SAMU":
        match = re.match(r"^(SA\d+MU)", code)
        return match.group(1) if match else code
    if family == "SAFU":
        match = re.match(r"^(SA\d+FU)", code)
        return match.group(1) if match else code
    if family == "HVA":
        match = re.match(r"^HVA(?:24|230)S?-(\d+)(Q)?", code)
        if match:
            return f"HVA-{match.group(1)}{'Q' if match.group(2) else ''}"
        return code
    if family == "HVD":
        match = re.match(r"^HVD(?:24|230)S?T?-(\d+)(Q|F)?", code)
        if match:
            return f"HVD-{match.group(1)}{match.group(2) or ''}"
        return code
    return code


@dataclass(frozen=True)
class ModelAttrGap:
    """One torque-family row with missing attribute slugs."""

    family: str
    model: str
    missing_slugs: tuple[str, ...]
    sku_codes: tuple[str, ...]


@dataclass(frozen=True)
class FamilyAttrCoverage:
    """Per-family counts for one attribute slug."""

    family: str
    slug: str
    ok: int
    missing: int


@dataclass(frozen=True)
class SeriesAttrGapReport:
    """Coverage + model-level gaps for scoped published SKUs."""

    coverage: tuple[FamilyAttrCoverage, ...]
    model_gaps: tuple[ModelAttrGap, ...]


def build_series_attr_gap_report(
    *,
    attr_slugs: Iterable[str] = DEFAULT_ATTR_SLUGS,
    published_only: bool = True,
) -> SeriesAttrGapReport:
    """Scan published DA/SA/HV SKUs for empty/missing attribute values."""
    slugs = tuple(dict.fromkeys(str(s).strip() for s in attr_slugs if str(s).strip()))
    qs = SKU.objects.all()
    if published_only:
        qs = qs.filter(is_published=True)
    sku_rows = list(qs.values_list("id", "sku_code"))
    sku_ids = [sid for sid, _ in sku_rows]
    present: dict[int, set[str]] = defaultdict(set)
    if sku_ids and slugs:
        for sid, slug in (
            AttributeValue.objects.filter(
                sku_id__in=sku_ids,
                attribute__slug__in=slugs,
            )
            .exclude(value="")
            .values_list("sku_id", "attribute__slug")
        ):
            present[sid].add(str(slug))

    # family -> slug -> ok/miss
    counts: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {slug: [0, 0] for slug in slugs},
    )
    # (family, model) -> missing slugs -> codes that miss at least one of them
    model_missing: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set),
    )

    for sid, code in sku_rows:
        family = series_family(str(code or ""))
        if family is None:
            continue
        have = present.get(sid, set())
        model = series_base_model(str(code or ""), family)
        for slug in slugs:
            if slug in have:
                counts[family][slug][0] += 1
            else:
                counts[family][slug][1] += 1
                model_missing[(family, model)][slug].add(str(code))

    coverage: list[FamilyAttrCoverage] = []
    for family in _FAMILY_ORDER:
        if family not in counts:
            continue
        for slug in slugs:
            ok, missing = counts[family][slug]
            coverage.append(
                FamilyAttrCoverage(family=family, slug=slug, ok=ok, missing=missing),
            )

    gaps: list[ModelAttrGap] = []
    for family, model in sorted(model_missing.keys(), key=lambda item: (_FAMILY_ORDER.index(item[0]), item[1])):
        miss_map = model_missing[(family, model)]
        missing_slugs = tuple(slug for slug in slugs if slug in miss_map)
        if not missing_slugs:
            continue
        codes: set[str] = set()
        for slug in missing_slugs:
            codes.update(miss_map[slug])
        gaps.append(
            ModelAttrGap(
                family=family,
                model=model,
                missing_slugs=missing_slugs,
                sku_codes=tuple(sorted(codes, key=str.upper)),
            ),
        )

    return SeriesAttrGapReport(coverage=tuple(coverage), model_gaps=tuple(gaps))


def format_series_attr_gap_report(report: SeriesAttrGapReport) -> str:
    """Human-readable stdout for the management command."""
    lines: list[str] = ["=== Family coverage ==="]
    by_family: dict[str, list[FamilyAttrCoverage]] = defaultdict(list)
    for row in report.coverage:
        by_family[row.family].append(row)
    for family in _FAMILY_ORDER:
        rows = by_family.get(family)
        if not rows:
            continue
        lines.append(f"\n{family}:")
        for row in rows:
            total = row.ok + row.missing
            lines.append(f"  {row.slug}: {row.ok}/{total} ok, miss={row.missing}")

    lines.append("\n=== Models with gaps (manual check) ===")
    if not report.model_gaps:
        lines.append("(none)")
        return "\n".join(lines)

    current_family = ""
    for gap in report.model_gaps:
        if gap.family != current_family:
            current_family = gap.family
            lines.append(f"\n{gap.family}:")
        miss = ", ".join(gap.missing_slugs)
        lines.append(f"  {gap.model}: missing {miss} ({len(gap.sku_codes)} SKU)")
    return "\n".join(lines)
