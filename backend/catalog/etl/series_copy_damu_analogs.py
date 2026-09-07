"""Curated «Аналоги» for DAMU (non-spring air) — Belimo catalog bands.

Belimo non-spring rotary (official EU datasheets):

- TMC = 2 Нм (~35 с)
- LM  = 5 Нм (~150 с)
- NM  = 10 Нм
- SM  = 20 Нм
- GM  = 40 Нм

Hoocon 4/6/8/16/24/32 Нм map to the *nearest* Belimo family (no invented
``NM24D`` / ``SM230D`` / torque-mismatched NM-on-16Нм cards).

DA2MU keeps the dedicated ``data/damu_2nm_analogs.txt`` (TMC + verified clones).
"""

from __future__ import annotations

from pathlib import Path

from catalog.etl.series_copy_major_analogs import _FOOTNOTE, _lines_major_air
from catalog.etl.tech_copy import normalize_tech_copy

_DAMU_2NM = Path(__file__).resolve().parent / "data" / "damu_2nm_analogs.txt"

# Nearest Belimo non-spring family for each Hoocon DAMU torque.
DAMU_BELIMO_NM: dict[int, int] = {
    2: 2,
    4: 5,
    6: 5,
    8: 10,
    16: 20,
    24: 20,
    32: 40,
}


def build_damu_analogs(nm: int) -> str:
    """Build edition-scoped analogs for DA..MU ``nm`` Нм."""
    if nm == 2:
        return normalize_tech_copy(_DAMU_2NM.read_text(encoding="utf-8").strip())

    band = DAMU_BELIMO_NM.get(nm, nm)
    blocks: list[str] = [
        (f"Список аналогов для привода заслонки Hoocon серии DA{nm}MU (без возвратной пружины, {nm} Нм)"),
        "",
        (
            "Belimo: ближайший класс по каталогу "
            f"(TMC 2 / LM 5 / NM 10 / SM 20 / GM 40 Нм) → полоса {band} Нм. "
            "Крупные марки: Belimo, Siemens, Honeywell, Schneider Electric, "
            "Johnson Controls, Danfoss, Gruner."
        ),
        "",
    ]
    for voltage in ("24", "230"):
        for modulating, aux, suf in (
            (False, False, "D"),
            (False, True, "DS"),
            (True, False, "A"),
            (True, True, "AS"),
        ):
            code = f"DA{nm}MU{voltage}-{suf}"
            mode = "пропорциональное (модулирующее) 0…10 В" if modulating else "2-/3-позиционное"
            aux_note = ", со вспомогательным(и) переключателем(ями)" if aux else ""
            blocks.append(f"Аналоги для {code} ({voltage} В, {mode}{aux_note}):")
            blocks.extend(
                _lines_major_air(
                    nm=band,
                    voltage=voltage,
                    modulating=modulating,
                    aux=aux,
                    fast=False,
                ),
            )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())
