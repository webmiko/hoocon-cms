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

from catalog.etl.series_copy_major_analogs import _FOOTNOTE
from catalog.etl.tech_copy import normalize_tech_copy

# Hoocon SAMU Nm → Belimo smoke family (no spring).
_SAMU_BELIMO: dict[int, tuple[str, str]] = {
    # (primary, secondary optional)
    10: ("BEN", "BLE"),  # 10 Нм → 15 Нм class (EMF-*-10 is not a Belimo actuator)
    15: ("BEN", "BLE"),
    30: ("BEE", "BE"),
}

# Hoocon DAFU Nm → Belimo spring-return air family.
_DAFU_BELIMO: dict[int, str] = {
    3: "TF",
    5: "LF",
    10: "NF",
    15: "SF",
    20: "SF",
}

# Hoocon SAFU Nm → Belimo fire family.
_SAFU_BELIMO: dict[int, str] = {
    3: "BFL",
    5: "BLF",
    10: "BFN",
    15: "BF",
    20: "BF",  # BF 18/12 Нм — ближайший к 20; BFL/BLF «-20N» в старых карточках — ошибка
}


def _smoke_belimo(family: str, voltage: str, *, thermal: bool) -> str:
    """Compose Belimo smoke-control article (BEN/BLE/BEE/BE)."""
    if family == "BEE":
        return f"Belimo BEE{voltage}{'ST' if thermal else ''}"
    code = f"Belimo {family}{voltage}"
    if thermal:
        code += "-T"
    return code


def _spring_air_belimo(family: str, voltage: str, *, modulating: bool, aux: bool) -> str:
    """Compose TF/LF/NF/SF article."""
    if family == "TF":
        code = f"TF{voltage}"
        if aux:
            code += "-S"
        return f"Belimo {code}"
    if family == "LF":
        # LF24 / LF24-S / LF24-RS (modulating)
        if modulating:
            code = f"LF{voltage}-RS"
        else:
            code = f"LF{voltage}"
            if aux:
                code += "-S"
        return f"Belimo {code}"
    # NF / SF — modern ``A`` generation
    code = f"{family}{voltage}A"
    if modulating:
        code += "-SR"
    if aux:
        code += "-S"
    return f"Belimo {code}"


def _fire_belimo(family: str, voltage: str, *, thermal: bool) -> str:
    """Compose BFL/BLF/BFN/BF article (2×SPDT built-in)."""
    code = f"Belimo {family}{voltage}"
    if thermal:
        code += "-T"
    return code


def build_samu_analogs(nm: int) -> str:
    """SA..MU smoke (no spring) — DS / DST × 24/230."""
    families = _SAMU_BELIMO.get(nm)
    if not families:
        raise ValueError(f"No Belimo smoke band for SA{nm}MU")
    primary, secondary = families
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки дымоудаления Hoocon "
            f"серии SA{nm}MU (без возвратной пружины, {nm} Нм)"
        ),
        "",
        (
            "Belimo smoke-control (каталог): BEN/BLE ≈ 15 Нм, BEE ≈ 25 Нм, "
            "BE ≈ 40 Нм. CM 2 Нм — не класс дымоудаления."
        ),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        "",
    ]
    for voltage in ("24", "230"):
        for thermal, suf in ((False, "DS"), (True, "DST")):
            code = f"SA{nm}MU{voltage}-{suf}"
            note = ", с термодатчиком" if thermal else ""
            blocks.append(f"{code} ({voltage} В, открыто/закрыто{note}):")
            blocks.append(f"– {_smoke_belimo(primary, voltage, thermal=thermal)}")
            if secondary != primary:
                blocks.append(f"– {_smoke_belimo(secondary, voltage, thermal=thermal)}")
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
    family = _DAFU_BELIMO.get(nm)
    if not family:
        raise ValueError(f"No Belimo spring band for DA{nm}FU")
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии DA{nm}FU "
            f"(с возвратной пружиной, {nm} Нм)"
        ),
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
            blocks.append(
                f"– {_spring_air_belimo(family, voltage, modulating=False, aux=aux)}",
            )
            blocks.append(
                f"– Siemens {'GCA' if voltage == '230' else 'GDB'}"
                f"{'126' if aux else '121'}.1E",
            )
            blocks.append("")
        # Modulating editions exist on 24 В cards for 5/10/15/20 Нм.
        if voltage == "24" and nm >= 5:
            for aux, suf in ((False, "A"), (True, "AS")):
                code = f"DA{nm}FU24-{suf}"
                blocks.append(
                    f"Аналоги для {code} (24 В, пропорциональное 0…10 В):",
                )
                blocks.append(
                    f"– {_spring_air_belimo(family, '24', modulating=True, aux=aux)}",
                )
                blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_safu_analogs(nm: int) -> str:
    """SA..FU fire damper — DS / DST × 24/230."""
    family = _SAFU_BELIMO.get(nm)
    if not family:
        raise ValueError(f"No Belimo fire band for SA{nm}FU")
    blocks: list[str] = [
        (
            f"Список аналогов для противопожарного привода Hoocon серии SA{nm}FU "
            f"(пружинный возврат, {nm} Нм)"
        ),
        "",
        (
            "Belimo fire (каталог): BFL ≈ 4/3, BLF ≈ 6/4, BFN ≈ 9/7, "
            "BF ≈ 18/12 Нм (мотор/пружина)."
        ),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner.",
        "",
    ]
    for voltage in ("24", "230"):
        for thermal, suf in ((False, "DS"), (True, "DST")):
            code = f"SA{nm}FU{voltage}-{suf}"
            note = ", с термодатчиком" if thermal else ""
            blocks.append(f"{code} ({voltage} В{note}):")
            blocks.append(f"– {_fire_belimo(family, voltage, thermal=thermal)}")
            # Compact US-style FSR/FST only for ~3 Нм.
            if nm <= 3:
                tag = "FST" if thermal else "FSR"
                blocks.append(f"– Belimo {tag}-{voltage}-3N")
            blocks.append(
                f"– Gruner 340{'TA' if thermal else ''}-{voltage}-"
                f"{'05' if nm <= 5 else '10'}-S2",
            )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())
