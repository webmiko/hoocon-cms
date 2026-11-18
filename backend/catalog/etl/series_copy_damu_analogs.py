"""Curated «Аналоги» for DAMU (non-spring air) — Belimo catalog bands.

Belimo non-spring rotary (official EU datasheets):

- TMC = 2 Нм (~35 с)
- LM  = 5 Нм (~150 с)
- NM  = 10 Нм
- SM  = 20 Нм
- GM  = 40 Нм

Hoocon 4/6/8/16/24/32 Нм map to the largest Belimo family whose damper area ≤ Hoocon's
(i.e. the Hoocon actuator covers at least the Belimo's rated area).

DA2MU keeps the dedicated ``data/damu_2nm_analogs.txt``.

A bullet «– Brand ARTICLE» would read as a confirmed pair. No pair here is
datasheet-confirmed, so the copy carries class guidance and the selection
footnote only — no edition blocks.
"""

from __future__ import annotations

from pathlib import Path

from catalog.etl.belimo_analogs import BELIMO_FAMILY_AREA, belimo_family_by_area
from catalog.etl.series_copy_major_analogs import _FOOTNOTE
from catalog.etl.tech_copy import normalize_tech_copy

_DAMU_2NM = Path(__file__).resolve().parent / "data" / "damu_2nm_analogs.txt"

# Recommended area of the largest Belimo family whose area ≤ Hoocon's.
# The guidance note in the copy keys off this Belimo area band.
_AIR_AREA = dict(BELIMO_FAMILY_AREA["air_no_spring"])
DAMU_BELIMO_NM: dict[int, int] = {
    nm: int(_AIR_AREA[family] * 10)
    for nm in (2, 4, 6, 8, 16, 24, 32)
    if (family := belimo_family_by_area("air_no_spring", nm / 10))
}


def build_damu_analogs(nm: int) -> str:
    """Guidance-only analogs copy for DA..MU ``nm`` Нм (no pair articles)."""
    if nm == 2:
        return normalize_tech_copy(_DAMU_2NM.read_text(encoding="utf-8").strip())

    band = DAMU_BELIMO_NM.get(nm, nm)
    blocks: list[str] = [
        (f"Список аналогов для привода заслонки Hoocon серии DA{nm}MU (без возвратной пружины, {nm} Нм)"),
        "",
        (
            "Belimo: наибольший класс, площадь которого не превышает площадь "
            f"заслонки Hoocon (TMC 2 / LM 5 / NM 10 / SM 20 / GM 40 Нм) → полоса {band} Нм. "
            "Крупные марки: Belimo, Siemens, Honeywell, Schneider Electric, "
            "Johnson Controls, Danfoss, Gruner."
        ),
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())
