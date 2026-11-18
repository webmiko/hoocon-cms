"""Curated spring / smoke / fire analogs — Belimo catalog bands only.

Sources (Belimo EU datasheets / shop):

Smoke control (no spring, form-fit 12×12). BLE is discontinued:
- BEN ≈ 15 Нм
- BEE ≈ 25 Нм
- BE  ≈ 40 Нм
(CM 2 Нм — compact *air*, not smoke-control.)

Spring-return air (DAFU):
- TF ≈ 2.5 Нм
- LF ≈ 4 Нм
- NF ≈ 10 Нм
- SF ≈ 20 Нм

Fire damper (SAFU, spring + 12×12):
- BFL ≈ 4/3 Нм
- BLF ≈ 6/4 Нм
- BFN ≈ 9/7 Нм
- BF  ≈ 18/12 Нм
"""

from __future__ import annotations

from catalog.etl.belimo_analogs import belimo_family_by_area
from catalog.etl.series_copy_major_analogs import _FOOTNOTE
from catalog.etl.tech_copy import normalize_tech_copy

_SAMU_NM = (10, 15, 30)
_SPRING_NM = (3, 5, 10, 15, 20)

# Hoocon Nm per series → Belimo family, largest whose area ≤ Hoocon area.
# None: even the smallest Belimo is stronger → no direct analog, no Belimo line.
_SAMU_BELIMO: dict[int, str | None] = {nm: belimo_family_by_area("smoke", nm / 10) for nm in _SAMU_NM}
_DAFU_BELIMO: dict[int, str | None] = {nm: belimo_family_by_area("air_spring", nm / 10) for nm in _SPRING_NM}
# SA20FU: BF 18/12 Нм is the largest compact fire actuator Belimo makes.
_SAFU_BELIMO: dict[int, str | None] = {nm: belimo_family_by_area("fire_spring", nm / 10) for nm in _SPRING_NM}


def build_samu_analogs(nm: int) -> str:
    """SA..MU smoke (no spring) — DS / DST × 24/230."""
    if nm not in _SAMU_BELIMO:
        raise ValueError(f"No SA{nm}MU smoke series")
    family = _SAMU_BELIMO[nm]
    blocks: list[str] = [
        (f"Список аналогов для привода заслонки дымоудаления Hoocon серии SA{nm}MU (без возвратной пружины, {nm} Нм)"),
        "",
    ]
    if family:
        blocks += [
            (
                "Belimo smoke-control (каталог): BEN ≈ 15 Нм, BEE ≈ 25 Нм, BE ≈ 40 Нм. "
                "CM 2 Нм — не класс дымоудаления. Термодатчик дымового клапана "
                "у Belimo — отдельное устройство, не суффикс привода."
            ),
            "",
            "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        ]
    else:
        blocks.append("Крупные марки: Siemens, Honeywell, Gruner.")
    blocks += ["", _FOOTNOTE]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_dafu_analogs(nm: int) -> str:
    """DA..FU spring-return air. Guidance only: no unverified pair articles."""
    if nm not in _DAFU_BELIMO:
        raise ValueError(f"No DA{nm}FU spring series")
    blocks: list[str] = [
        (f"Список аналогов для привода заслонки Hoocon серии DA{nm}FU (с возвратной пружиной, {nm} Нм)"),
        "",
        (
            "Belimo spring-return air (каталог): TF ≈ 2.5 / LF ≈ 4 / NF ≈ 10 / "
            "SF ≈ 20 Нм. BF/BX — противопожарный класс, не воздушный spring."
        ),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_safu_analogs(nm: int) -> str:
    """SA..FU fire damper. Guidance only: no unverified pair articles."""
    if nm not in _SAFU_BELIMO:
        raise ValueError(f"No SA{nm}FU fire series")
    blocks: list[str] = [
        (f"Список аналогов для противопожарного привода Hoocon серии SA{nm}FU (пружинный возврат, {nm} Нм)"),
        "",
        ("Belimo fire (каталог): BFL ≈ 4/3, BLF ≈ 6/4, BFN ≈ 9/7, BF ≈ 18/12 Нм (мотор/пружина)."),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())
