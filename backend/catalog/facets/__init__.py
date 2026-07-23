"""Canonical ТТХ facets for catalog filters and card highlights.

Tilda ETL creates duplicate Attribute rows with opaque ``attr-<id>`` slugs.
Public API exposes stable facet keys (``moment``, ``voltage``, …) that match
by Attribute.name patterns (and optional legacy slugs).

Spec: docs/plan-detail-mvp.md S2; docs/market-analysis.md B2.
"""

from __future__ import annotations

from catalog.facets.aux import (
    AUX_SWITCH_NONE,
    AUX_SWITCH_SPDT_1,
    AUX_SWITCH_SPDT_2,
    aux_spdt_count_from_sku,
    format_aux_switch_display,
    normalize_aux_switch_value,
)
from catalog.facets.copy import (
    extract_sku_lead,
    format_sku_heading_name,
    paraphrase_sku_lead,
    strip_attribute_echo_from_text,
    strip_heading_echo_from_description,
    strip_lead_duplicate_lines,
)
from catalog.facets.dedupe import dedupe_attribute_values
from catalog.facets.defs import (
    EXTRA_HIGHLIGHT_DEFS,
    FACET_BY_KEY,
    FACET_DEFS,
    FACET_KEYS,
    FacetDef,
    attribute_ids_for_facet,
    attribute_matches_facet,
)
from catalog.facets.filter_options import (
    _facet_sort_key,
    collect_facet_options,
    filter_skus_by_facet,
)
from catalog.facets.highlights import (
    ensure_modulating_signal_attributes,
    highlights_for_sku,
)
from catalog.facets.normalize import (
    normalize_area_attribute_value,
    normalize_facet_value,
    strip_facet_parenthetical,
    values_match,
)

__all__ = [
    "AUX_SWITCH_NONE",
    "AUX_SWITCH_SPDT_1",
    "AUX_SWITCH_SPDT_2",
    "EXTRA_HIGHLIGHT_DEFS",
    "FACET_BY_KEY",
    "FACET_DEFS",
    "FACET_KEYS",
    "FacetDef",
    "_facet_sort_key",
    "attribute_ids_for_facet",
    "attribute_matches_facet",
    "aux_spdt_count_from_sku",
    "collect_facet_options",
    "dedupe_attribute_values",
    "ensure_modulating_signal_attributes",
    "extract_sku_lead",
    "filter_skus_by_facet",
    "format_aux_switch_display",
    "format_sku_heading_name",
    "highlights_for_sku",
    "normalize_area_attribute_value",
    "normalize_aux_switch_value",
    "normalize_facet_value",
    "paraphrase_sku_lead",
    "strip_attribute_echo_from_text",
    "strip_facet_parenthetical",
    "strip_heading_echo_from_description",
    "strip_lead_duplicate_lines",
    "values_match",
]
