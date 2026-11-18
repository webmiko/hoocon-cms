"""Verified Belimo pairs for the spring-return DA…FU / SA…FU families.

Критерии те же, что в 0024: момент Belimo ≥ серии Hoocon, тип
управления и напряжение совпадают, вспомогательные контакты и
термодатчик учтены явно. Без пары: модулирующие 230 В (у Belimo
нет), SA20FU сверх максимальной механической пружины отмечен в note.

Факты из даташитов Belimo:
- Spring-return air: LF 4, NF 10, SF 20 Нм; ``-S2`` = 2×SPDT,
  ``-SR`` = модулирующий только 24 В, ``-SR-S2`` = мод. + 2×SPDT
  (NF24A-SR-S2, SF24A-SR-S2 — актуальные артикулы).
- LF — компактный корпус: интегрированного варианта с 2×SPDT нет
  (LF24-S = 1 контакт) → второй контакт через блок S2A.
- Fire damper (противопожарные, вал 12×12): BFL 4/3, BLF 6/4,
  BFN 9/7, BF 18/12 Нм (мотор/пружина); ``-T`` = терморасцепитель
  BAT 72 °C (BFL…BFN -T — актуальные; BF24-T/BF230-T выведены →
  для SA…FU-DST на BF: базовый + отдельный BAT72).
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
_C_MOD = "0(2)…10 В"

_ACC = "вспом. контакты — навесной блок Belimo S2A"
_BAT = "терморасцепитель 72 °C — отдельное устройство Belimo BAT72"
_LFAUX = "у LF только 1 встроенный контакт (-S); 2×SPDT — блок S2A"
_SPR = "пружинный возврат"


def _row(code: str, nm: int | None, voltage: str, control: str, note: str = ""):
    """Short pair-spec builder: (foreign_code, torque_nm, voltage, control, note)."""
    return code, nm, voltage, control, note


def _dafu(family: str, belimo: str, nm: int, torque_note: str = "") -> dict[str, tuple]:
    """DA…FU spring-return pair set (-D/-DS/-A/-AS 24 В; -D/-DS 230 В)."""
    return {
        f"{family}24-D": _row(f"{belimo}24A", nm, _V24, _C_ONOFF, f"{_SPR}; {torque_note}".rstrip("; ")),
        f"{family}24-DS": _row(f"{belimo}24A-S2", nm, _V24, _C_ONOFF, f"{_SPR}, 2×SPDT; {torque_note}".rstrip("; ")),
        f"{family}24-A": _row(f"{belimo}24A-SR", nm, _V24, _C_MOD, f"{_SPR}; {torque_note}".rstrip("; ")),
        f"{family}24-AS": _row(f"{belimo}24A-SR-S2", nm, _V24, _C_MOD, f"{_SPR}, 2×SPDT; {torque_note}".rstrip("; ")),
        f"{family}230-D": _row(f"{belimo}230A", nm, _V230, _C_ONOFF, f"{_SPR}; {torque_note}".rstrip("; ")),
        f"{family}230-DS": _row(
            f"{belimo}230A-S2", nm, _V230, _C_ONOFF, f"{_SPR}, 2×SPDT; {torque_note}".rstrip("; ")
        ),
    }


def _safu(family: str, belimo: str, nm: int, torque_note: str = "") -> dict[str, tuple]:
    """SA…FU fire-damper pair set (-DS откр/закр, -DST + терморасцепитель)."""
    return {
        f"{family}24-DS": _row(f"{belimo}24", nm, _V24, _C_ONOFF, f"{_SPR}, 2×SPDT; {torque_note}".rstrip("; ")),
        f"{family}24-DST": _row(
            f"{belimo}24-T", nm, _V24, _C_ONOFF, f"{_SPR}, 2×SPDT + BAT 72 °C; {torque_note}".rstrip("; ")
        ),
        f"{family}230-DS": _row(f"{belimo}230", nm, _V230, _C_ONOFF, f"{_SPR}, 2×SPDT; {torque_note}".rstrip("; ")),
        f"{family}230-DST": _row(
            f"{belimo}230-T", nm, _V230, _C_ONOFF, f"{_SPR}, 2×SPDT + BAT 72 °C; {torque_note}".rstrip("; ")
        ),
    }


def _safu_bf(family: str, torque_note: str = "") -> dict[str, tuple]:
    """SA…FU on BF (18/12 Нм): -T исполнение выведено → базовый + BAT72."""
    rows = _safu(family, "BF", 18, torque_note)
    rows[f"{family}24-DST"] = _row("BF24", 18, _V24, _C_ONOFF, f"{_SPR}, 2×SPDT; {_BAT}; {torque_note}".rstrip("; "))
    rows[f"{family}230-DST"] = _row(
        "BF230", 18, _V230, _C_ONOFF, f"{_SPR}, 2×SPDT; {_BAT}; {torque_note}".rstrip("; ")
    )
    return rows


_PAIRS: dict[str, tuple] = {
    # ── DA3FU 3 Нм → LF 4 Нм (компакт: 2-й контакт только блоком S2A) ──
    "DA3FU24-D": _row("LF24", 4, _V24, _C_ONOFF, f"{_SPR}; 4 Нм ≥ 3"),
    "DA3FU24-DS": _row("LF24", 4, _V24, _C_ONOFF, f"{_SPR}; {_LFAUX}"),
    "DA3FU24-A": _row("LF24-SR", 4, _V24, _C_MOD, f"{_SPR}; 4 Нм ≥ 3"),
    "DA3FU24-AS": _row("LF24-SR", 4, _V24, _C_MOD, f"{_SPR}; {_LFAUX}"),
    "DA3FU230-D": _row("LF230", 4, _V230, _C_ONOFF, f"{_SPR}; 4 Нм ≥ 3"),
    "DA3FU230-DS": _row("LF230", 4, _V230, _C_ONOFF, f"{_SPR}; {_LFAUX}"),
    # ── DA…FU 5/10 Нм → NF 10 Нм; 15/20 Нм → SF 20 Нм ──
    **_dafu("DA5FU", "NF", 10, "10 Нм ≥ 5"),
    **_dafu("DA10FU", "NF", 10),
    **_dafu("DA15FU", "SF", 20, "20 Нм ≥ 15"),
    **_dafu("DA20FU", "SF", 20),
    # ── SA…FU противопожарные (DS откр/закр, DST + термодатчик) ──
    **_safu("SA3FU", "BFL", 4, "мотор/пружина 4/3 Нм ≥ 3"),
    **_safu("SA5FU", "BLF", 6, "мотор/пружина 6/4 Нм ≥ 5"),
    # BFN 9/7 < 10 — берём BF 18/12; -T у BF выведен → базовый + BAT72
    **_safu_bf("SA10FU", "мотор/пружина 18/12 Нм ≥ 10 (BFN 9 < 10)"),
    **_safu_bf("SA15FU", "мотор/пружина 18/12 Нм ≥ 15"),
    **_safu_bf("SA20FU", "мотор 18 Нм < 20 — максимум у Belimo, сверить запас"),
}


def forwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    AnalogMap = apps.get_model("catalog", "AnalogMap")
    SKU = apps.get_model("catalog", "SKU")
    missing: list[str] = []
    created = 0
    for sku_code, (foreign_code, nm, voltage, control, note) in _PAIRS.items():
        sku = SKU.objects.filter(sku_code__iexact=sku_code).first()
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
                "spring_return": True,
                "note": note,
                "is_active": True,
            },
        )
        created += int(was_created)
    if missing:
        print(f"\n  AnalogMap: {len(missing)} SKU не найдено (пропущено): {', '.join(sorted(missing))}")
    print(f"\n  AnalogMap: создано {created} верифицированных пар Belimo (FU)")


def backwards(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    AnalogMap = apps.get_model("catalog", "AnalogMap")
    keys = {"".join(ch for ch in code.upper() if ch.isalnum()) for code, *_ in _PAIRS.values()}
    AnalogMap.objects.filter(brand="Belimo", foreign_code_key__in=keys).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0024_analogmap_belimo_verified"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
