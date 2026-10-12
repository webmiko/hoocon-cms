"""Curated spring / smoke / fire analogs — Belimo catalog bands only.

Sources (Belimo EU datasheets / shop):

Smoke control (no spring, form-fit 12×12):
- BEN / BLE ≈ 15 Нм
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

from catalog.etl.belimo_analogs import belimo_family_by_area, compose_belimo_article
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


def _belimo_lines(
    families: tuple[str | None, ...],
    voltage: str,
    *,
    modulating: bool = False,
    aux: bool = False,
    thermal: bool = False,
) -> list[str]:
    """«– Belimo …» bullets for families that have a direct analog of this edition."""
    lines: list[str] = []
    for family in families:
        if family is None:
            continue
        code = compose_belimo_article(family, voltage=voltage, modulating=modulating, aux=aux, thermal=thermal)
        if code:
            lines.append(f"– Belimo {code}")
    return lines


def build_samu_analogs(nm: int) -> str:
    """SA..MU smoke (no spring) — DS / DST × 24/230."""
    if nm not in _SAMU_BELIMO:
        raise ValueError(f"No SA{nm}MU smoke series")
    family = _SAMU_BELIMO[nm]
    # BLE is the second 15 Нм smoke model next to BEN.
    families = (family, "BLE") if family == "BEN" else (family,)
    blocks: list[str] = [
        (f"Список аналогов для привода заслонки дымоудаления Hoocon серии SA{nm}MU (без возвратной пружины, {nm} Нм)"),
        "",
    ]
    if family:
        blocks += [
            (
                "Belimo smoke-control (каталог): BEN/BLE ≈ 15 Нм, BEE ≈ 25 Нм, BE ≈ 40 Нм. "
                "CM 2 Нм — не класс дымоудаления."
            ),
            "",
            "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        ]
    else:
        blocks.append("Крупные марки: Siemens, Honeywell, Gruner.")
    blocks.append("")
    for voltage in ("24", "230"):
        for thermal, suf in ((False, "DS"), (True, "DST")):
            code = f"SA{nm}MU{voltage}-{suf}"
            note = ", с термодатчиком" if thermal else ""
            blocks.append(f"{code} ({voltage} В, открыто/закрыто{note}):")
            blocks.extend(_belimo_lines(families, voltage, aux=True, thermal=thermal))
            if thermal:
                blocks.append("– Siemens GIB161.1E")
                blocks.append(
                    f"– Honeywell {'MS4120F1006' if voltage == '24' else 'MS4120F1206'}",
                )
                blocks.append(f"– Gruner 340TA-{voltage}-10-S2")
            else:
                blocks.append("– Siemens GIB131.1E")
                blocks.append(
                    f"– Honeywell {'MS4120F1006' if voltage == '24' else 'MS4120F1206'}",
                )
                blocks.append(f"– Johnson Controls M9220-AGA-{voltage}")
                blocks.append(f"– Gruner 340-{voltage}-10-S2")
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_dafu_analogs(nm: int) -> str:
    """DA..FU spring-return air — D/DS (+ A/AS when 24 В modulating exists)."""
    if nm not in _DAFU_BELIMO:
        raise ValueError(f"No DA{nm}FU spring series")
    family = _DAFU_BELIMO[nm]
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
    ]
    for voltage in ("24", "230"):
        for modulating, aux, suf in (
            (False, False, "D"),
            (False, True, "DS"),
        ):
            code = f"DA{nm}FU{voltage}-{suf}"
            blocks.append(f"Аналоги для {code} ({voltage} В, 2-/3-позиционное):")
            blocks.extend(_belimo_lines((family,), voltage, aux=aux))
            blocks.append(
                f"– Siemens {'GCA' if voltage == '230' else 'GDB'}{'126' if aux else '121'}.1E",
            )
            blocks.append("")
        # Modulating editions exist on 24 В cards for 5/10/15/20 Нм.
        if voltage == "24" and nm >= 5:
            for aux, suf in ((False, "A"), (True, "AS")):
                blocks.append(
                    f"Аналоги для DA{nm}FU24-{suf} (24 В, пропорциональное 0…10 В):",
                )
                # Keep the edition block: without it the A block's Belimo would match AS by prefix.
                lines = _belimo_lines((family,), "24", modulating=True, aux=aux)
                blocks.extend(lines or ["– Прямого аналога среди крупных марок нет."])
                blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_safu_analogs(nm: int) -> str:
    """SA..FU fire damper — DS / DST × 24/230."""
    if nm not in _SAFU_BELIMO:
        raise ValueError(f"No SA{nm}FU fire series")
    family = _SAFU_BELIMO[nm]
    blocks: list[str] = [
        (f"Список аналогов для противопожарного привода Hoocon серии SA{nm}FU (пружинный возврат, {nm} Нм)"),
        "",
        ("Belimo fire (каталог): BFL ≈ 4/3, BLF ≈ 6/4, BFN ≈ 9/7, BF ≈ 18/12 Нм (мотор/пружина)."),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        "",
    ]
    for voltage in ("24", "230"):
        for thermal, suf in ((False, "DS"), (True, "DST")):
            code = f"SA{nm}FU{voltage}-{suf}"
            note = ", с термодатчиком" if thermal else ""
            blocks.append(f"{code} ({voltage} В{note}):")
            blocks.extend(_belimo_lines((family,), voltage, aux=True, thermal=thermal))
            # Compact US-style FSR/FST only for ~3 Нм.
            if nm <= 3:
                tag = "FST" if thermal else "FSR"
                blocks.append(f"– Belimo {tag}-{voltage}-3N")
            blocks.append(
                f"– Gruner 340{'TA' if thermal else ''}-{voltage}-{'05' if nm <= 5 else '10'}-S2",
            )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())
