"""Verified Belimo replacement pairs curated against Belimo datasheets.

Каждая пара проверена по критериям: момент ≥ Hoocon, тип управления
совпадает, напряжение совпадает (24/230), вспомогательные контакты,
термодатчик, посадка на вал. Где у Belimo нет точного ответа
(230 В модулирующие, быстрые >16 Нм, fail-safe >30 Нм, 230 В
модулирующий fail-safe) — пара НЕ ставится.

Факты из даташитов Belimo:
- Стандарт: LM 5 / NM 10 / SM 20 / GM 40 Нм; ``-S`` = 1×SPDT,
  ``-S2`` = 2×SPDT, ``-SR`` = модулирующий только 24 В;
  230 В модулирующих нет.
- Быстрые: LMQ 4 Нм/2.5 c, NMQ 8 Нм/4 c, SMQ 16 Нм/7 c — только 24 В
  (NMD230A/SMD230A — 20 c, это НЕ быстрые).
- Fail-safe электронный: EF24A(-S2/-SR/-SR-S2), EF230A(-S2) — 30 Нм;
  230 В модулирующего EF нет.
- Пожарные с пружиной: BFL 4/3, BLF 6/4, BFN 9/7, BF 18/12 Нм;
  ``-T`` = терморасцепитель 72 °C (BF24-T/BF230-T выведены из
  производства → для 10F термо: BF… + отдельный BAT72).
- Дымовые без пружины (OEM): BEN 15, BEE 25, BE 40 Нм, 2×SPDT
  встроенные; BE24/BE230 = вал 14×14, ``-12`` = 12×12;
  терморасцепитель — отдельное устройство BAT72.
- Компакт: CM24-L/-R, CM24-SR-L/-R, CM230-L/-R — 2 Нм,
  направление фиксированное, вспомогательных контактов нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.apps.registry import Apps
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_V24 = "AC/DC 24 В"
_V230 = "AC 230 В"
_C_ONOFF = "откр/закр"
_C_MOD = "0…10 В"

_ACC = "вспом. контакты — навесной блок Belimo S2A"
_AUX1 = "у CM вспом. контактов нет — внешний блок"
_BAT = "терморасцепитель 72 °C — отдельное устройство Belimo BAT72"
_OEM = "OEM-серия: поставка через производителей дымовых заслонок"
_DIR = "направление вращения фиксированное (-L; зеркально — …-R)"


def _row(code: str, nm: int | None, voltage: str, control: str, note: str = ""):
    """Short pair-spec builder: (foreign_code, torque_nm, voltage, control, note)."""
    return code, nm, voltage, control, note


def _std(family: str, belimo: str, nm: int, torque_note: str = "") -> dict[str, tuple]:
    """Standard on/off+3-pos pair set for a DA…MU torque class.

    Generates pairs for -D/-DS/-A/-AS (24 В) and -D/-DS (230 В).
    230 В модулирующих у Belimo нет — -A/-AS 230 В без пары.
    """
    aux = "2×SPDT"
    return {
        f"{family}24-D": _row(f"{belimo}24A", nm, _V24, _C_ONOFF, torque_note),
        f"{family}24-DS": _row(f"{belimo}24A-S2", nm, _V24, _C_ONOFF, f"{aux}; {torque_note}".rstrip("; ")),
        f"{family}24-A": _row(f"{belimo}24A-SR", nm, _V24, _C_MOD, torque_note),
        f"{family}24-AS": _row(f"{belimo}24A-SR", nm, _V24, _C_MOD, f"{_ACC}; {torque_note}".rstrip("; ")),
        f"{family}230-D": _row(f"{belimo}230A", nm, _V230, _C_ONOFF, torque_note),
        f"{family}230-DS": _row(f"{belimo}230A-S2", nm, _V230, _C_ONOFF, f"{aux}; {torque_note}".rstrip("; ")),
    }


def _fast(family: str, belimo: str, nm: int, speed: str) -> dict[str, tuple]:
    """Fast 24 В pair set for DA…MQU / HVA-Q / HVD-Q."""
    return {
        f"{family}24-D": _row(f"{belimo}24A", nm, _V24, _C_ONOFF, f"быстрый {speed}"),
        f"{family}24-DS": _row(f"{belimo}24A", nm, _V24, _C_ONOFF, f"быстрый {speed}; {_ACC}"),
        f"{family}24-A": _row(f"{belimo}24A-SR", nm, _V24, _C_MOD, f"быстрый {speed}"),
        f"{family}24-AS": _row(f"{belimo}24A-SR", nm, _V24, _C_MOD, f"быстрый {speed}; {_ACC}"),
    }


_PAIRS: dict[str, tuple] = {
    # ── DA2MU 2 Нм — компактная серия CM, направление фикс. ──
    "DA2MU24-D": _row("CM24-L", 2, _V24, _C_ONOFF, _DIR),
    "DA2MU24-DS": _row("CM24-L", 2, _V24, _C_ONOFF, f"{_DIR}; {_AUX1}"),
    "DA2MU24-A": _row("CM24-SR-L", 2, _V24, _C_MOD, _DIR),
    "DA2MU24-AS": _row("CM24-SR-L", 2, _V24, _C_MOD, f"{_DIR}; {_AUX1}"),
    "DA2MU230-D": _row("CM230-L", 2, _V230, _C_ONOFF, _DIR),
    "DA2MU230-DS": _row("CM230-L", 2, _V230, _C_ONOFF, f"{_DIR}; {_AUX1}"),
    # ── DA…MU стандартные без пружины ──
    **_std("DA4MU", "LM", 5),
    **_std("DA6MU", "NM", 10),
    **_std("DA8MU", "NM", 10),
    **_std("DA16MU", "SM", 20),
    **_std("DA24MU", "GM", 40, "40 Нм ≥ 24"),
    **_std("DA32MU", "GM", 40, "40 Нм ≥ 32"),
    # ── DA…MQU ускоренные 24 В (Belimo fast: NMQ 8, SMQ 16) ──
    **_fast("DA5MQU", "NMQ", 8, "4 с/90°, 8 Нм ≥ 5"),
    **_fast("DA8MQU", "NMQ", 8, "4 с/90°"),
    **_fast("DA10MQU", "SMQ", 16, "7 с/90°, 16 Нм ≥ 10"),
    **_fast("DA16MQU", "SMQ", 16, "7 с/90°"),
    # DA20/24MQU и все MQU230 — пары нет: быстрых Belimo >16 Нм и 230 В нет
    # ── HVA модулирующие 24 В ──
    "HVA24-2": _row("CM24-SR-L", 2, _V24, _C_MOD, _DIR),
    "HVA24S-2": _row("CM24-SR-L", 2, _V24, _C_MOD, f"{_DIR}; {_AUX1}"),
    "HVA24-5": _row("LM24A-SR", 5, _V24, _C_MOD),
    "HVA24S-5": _row("LM24A-SR", 5, _V24, _C_MOD, _ACC),
    "HVA24-10": _row("NM24A-SR", 10, _V24, _C_MOD),
    "HVA24S-10": _row("NM24A-SR", 10, _V24, _C_MOD, _ACC),
    "HVA24-20": _row("SM24A-SR", 20, _V24, _C_MOD),
    "HVA24S-20": _row("SM24A-SR", 20, _V24, _C_MOD, _ACC),
    "HVA24-40": _row("GM24A-SR", 40, _V24, _C_MOD),
    "HVA24S-40": _row("GM24A-SR", 40, _V24, _C_MOD, _ACC),
    # HVA-Q ускоренные модулирующие
    "HVA24-5Q": _row("NMQ24A-SR", 8, _V24, _C_MOD, "быстрый 4 с/90°, 8 Нм ≥ 5"),
    "HVA24S-5Q": _row("NMQ24A-SR", 8, _V24, _C_MOD, f"быстрый 4 с/90°; {_ACC}"),
    "HVA24-8Q": _row("NMQ24A-SR", 8, _V24, _C_MOD, "быстрый 4 с/90°"),
    "HVA24S-8Q": _row("NMQ24A-SR", 8, _V24, _C_MOD, f"быстрый 4 с/90°; {_ACC}"),
    "HVA24-10Q": _row("SMQ24A-SR", 16, _V24, _C_MOD, "быстрый 7 с/90°, 16 Нм ≥ 10"),
    "HVA24S-10Q": _row("SMQ24A-SR", 16, _V24, _C_MOD, f"быстрый 7 с/90°; {_ACC}"),
    # HVA-QX конденсаторный fail-safe → EF 30 Нм (модулирующий только 24 В)
    "HVA24-5QX": _row("EF24A-SR", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм"),
    "HVA24S-5QX": _row("EF24A-SR-S2", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVA24-10QX": _row("EF24A-SR", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм"),
    "HVA24S-10QX": _row("EF24A-SR-S2", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVA24-20QX": _row("EF24A-SR", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм"),
    "HVA24S-20QX": _row("EF24A-SR-S2", 30, _V24, _C_MOD, "электронный fail-safe 30 Нм, 2×SPDT"),
    # HVA230-* (все) — нет 230 В модулирующих; HVA*UQ — назначение не подтверждено
    # ── HVD откр/закр без пружины ──
    "HVD24-5": _row("LM24A", 5, _V24, _C_ONOFF),
    "HVD24S-5": _row("LM24A-S2", 5, _V24, _C_ONOFF, "2×SPDT"),
    "HVD230-5": _row("LM230A", 5, _V230, _C_ONOFF),
    "HVD230S-5": _row("LM230A-S2", 5, _V230, _C_ONOFF, "2×SPDT"),
    "HVD24-10": _row("NM24A", 10, _V24, _C_ONOFF),
    "HVD24S-10": _row("NM24A-S2", 10, _V24, _C_ONOFF, "2×SPDT"),
    "HVD230-10": _row("NM230A", 10, _V230, _C_ONOFF),
    "HVD230S-10": _row("NM230A-S2", 10, _V230, _C_ONOFF, "2×SPDT"),
    "HVD24-20": _row("SM24A", 20, _V24, _C_ONOFF),
    "HVD24S-20": _row("SM24A-S2", 20, _V24, _C_ONOFF, "2×SPDT"),
    "HVD230-20": _row("SM230A", 20, _V230, _C_ONOFF),
    "HVD230S-20": _row("SM230A-S2", 20, _V230, _C_ONOFF, "2×SPDT"),
    "HVD24-40": _row("GM24A", 40, _V24, _C_ONOFF),
    "HVD24S-40": _row("GM24A-S2", 40, _V24, _C_ONOFF, "2×SPDT"),
    "HVD230-40": _row("GM230A", 40, _V230, _C_ONOFF),
    "HVD230S-40": _row("GM230A-S2", 40, _V230, _C_ONOFF, "2×SPDT"),
    # HVD-Q ускоренные откр/закр (24 В)
    "HVD24-5Q": _row("NMQ24A", 8, _V24, _C_ONOFF, "быстрый 4 с/90°, 8 Нм ≥ 5"),
    "HVD24S-5Q": _row("NMQ24A", 8, _V24, _C_ONOFF, f"быстрый 4 с/90°; {_ACC}"),
    "HVD24-10Q": _row("SMQ24A", 16, _V24, _C_ONOFF, "быстрый 7 с/90°, 16 Нм ≥ 10"),
    "HVD24S-10Q": _row("SMQ24A", 16, _V24, _C_ONOFF, f"быстрый 7 с/90°; {_ACC}"),
    # HVD-QX конденсаторный fail-safe → EF (откр/закр, 24 и 230 В)
    "HVD24-5QX": _row("EF24A", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD24S-5QX": _row("EF24A-S2", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVD24-10QX": _row("EF24A", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD24S-10QX": _row("EF24A-S2", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVD24-20QX": _row("EF24A", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD24S-20QX": _row("EF24A-S2", 30, _V24, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVD230-5QX": _row("EF230A", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD230S-5QX": _row("EF230A-S2", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVD230-10QX": _row("EF230A", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD230S-10QX": _row("EF230A-S2", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    "HVD230-20QX": _row("EF230A", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм"),
    "HVD230S-20QX": _row("EF230A-S2", 30, _V230, _C_ONOFF, "электронный fail-safe 30 Нм, 2×SPDT"),
    # ── HVD-…F пожарные с пружиной → Belimo fire (мотор/пружина), -T = BAT 72 °C ──
    "HVD24S-3F": _row("BFL24", 4, _V24, _C_ONOFF, "4/3 Нм, 2×SPDT"),
    "HVD24ST-3F": _row("BFL24-T", 4, _V24, _C_ONOFF, "4/3 Нм + терморасцепитель 72 °C"),
    "HVD230S-3F": _row("BFL230", 4, _V230, _C_ONOFF, "4/3 Нм, 2×SPDT"),
    "HVD230ST-3F": _row("BFL230-T", 4, _V230, _C_ONOFF, "4/3 Нм + терморасцепитель 72 °C"),
    "HVD24S-5F": _row("BLF24", 6, _V24, _C_ONOFF, "6/4 Нм, 2×SPDT"),
    "HVD24ST-5F": _row("BLF24-T", 6, _V24, _C_ONOFF, "6/4 Нм + терморасцепитель 72 °C"),
    "HVD230S-5F": _row("BLF230", 6, _V230, _C_ONOFF, "6/4 Нм, 2×SPDT"),
    "HVD230ST-5F": _row("BLF230-T", 6, _V230, _C_ONOFF, "6/4 Нм + терморасцепитель 72 °C"),
    "HVD24S-10F": _row("BF24", 18, _V24, _C_ONOFF, "18/12 Нм, 2×SPDT"),
    "HVD24ST-10F": _row("BF24", 18, _V24, _C_ONOFF, f"18/12 Нм, 2×SPDT; {_BAT}"),
    "HVD24SX-10F": _row("BF24", 18, _V24, _C_ONOFF, f"18/12 Нм, 2×SPDT; {_BAT} (канальный)"),
    "HVD230S-10F": _row("BF230", 18, _V230, _C_ONOFF, "18/12 Нм, 2×SPDT"),
    "HVD230ST-10F": _row("BF230", 18, _V230, _C_ONOFF, f"18/12 Нм, 2×SPDT; {_BAT}"),
    "HVD230SX-10F": _row("BF230", 18, _V230, _C_ONOFF, f"18/12 Нм, 2×SPDT; {_BAT} (канальный)"),
    # ── SA…MU дымовые без пружины → Belimo smoke OEM (2×SPDT встроены) ──
    "SA7MU24-DS": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм ≥ 7, 2×SPDT; {_OEM}"),
    "SA7MU24-DST": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм ≥ 7; {_BAT}; {_OEM}"),
    "SA7MU230-DS": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм ≥ 7, 2×SPDT; {_OEM}"),
    "SA7MU230-DST": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм ≥ 7; {_BAT}; {_OEM}"),
    "SA10MU24-DS": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм ≥ 10, 2×SPDT; {_OEM}"),
    "SA10MU24-DST": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм ≥ 10; {_BAT}; {_OEM}"),
    "SA10MU230-DS": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм ≥ 10, 2×SPDT; {_OEM}"),
    "SA10MU230-DST": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм ≥ 10; {_BAT}; {_OEM}"),
    "SA15MU24-DS": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм, 2×SPDT; {_OEM}"),
    "SA15MU24-DST": _row("BEN24", 15, _V24, _C_ONOFF, f"дымовой 15 Нм; {_BAT}; {_OEM}"),
    "SA15MU230-DS": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм, 2×SPDT; {_OEM}"),
    "SA15MU230-DST": _row("BEN230", 15, _V230, _C_ONOFF, f"дымовой 15 Нм; {_BAT}; {_OEM}"),
    "SA30MU24-DS": _row("BE24-12", 40, _V24, _C_ONOFF, f"дымовой 40 Нм ≥ 30, вал 12×12; {_OEM}"),
    "SA30MU24-DST": _row("BE24-12", 40, _V24, _C_ONOFF, f"дымовой 40 Нм ≥ 30, вал 12×12; {_BAT}; {_OEM}"),
    "SA30MU230-DS": _row("BE230-12", 40, _V230, _C_ONOFF, f"дымовой 40 Нм ≥ 30, вал 12×12; {_OEM}"),
    "SA30MU230-DST": _row("BE230-12", 40, _V230, _C_ONOFF, f"дымовой 40 Нм ≥ 30, вал 12×12; {_BAT}; {_OEM}"),
}


def _is_spring(sku_code: str) -> bool:
    """HVD-…F — единственные пружинные в таблице (QX — электронный fail-safe)."""
    return sku_code.startswith("HVD") and sku_code.endswith("F")


def forwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    AnalogMap = apps.get_model("catalog", "AnalogMap")
    SKU = apps.get_model("catalog", "SKU")
    missing: list[str] = []
    created = 0
    for sku_code, (foreign_code, nm, voltage, control, note) in _PAIRS.items():
        sku = SKU.objects.filter(sku_code=sku_code).first()
        if sku is None:
            missing.append(sku_code)
            continue
        key = "".join(ch for ch in foreign_code.upper() if ch.isalnum())
        _, was_created = AnalogMap.objects.get_or_create(
            brand="Belimo",
            foreign_code_key=key,
            sku=sku,
            defaults={
                "foreign_code": foreign_code,
                "torque_nm": nm,
                "voltage": voltage,
                "control": control,
                "spring_return": _is_spring(sku_code),
                "note": note,
                "is_active": True,
            },
        )
        created += int(was_created)
    if missing:
        print(f"\n  AnalogMap: {len(missing)} SKU не найдено (пропущено): {', '.join(sorted(missing))}")
    print(f"\n  AnalogMap: создано {created} верифицированных пар Belimo")


def backwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    AnalogMap = apps.get_model("catalog", "AnalogMap")
    keys = {"".join(ch for ch in code.upper() if ch.isalnum()) for code, *_ in _PAIRS.values()}
    AnalogMap.objects.filter(brand="Belimo", foreign_code_key__in=keys).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0023_analogmap_uniq_per_sku"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
