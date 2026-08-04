#!/usr/bin/env python3
"""Build RU A4×2 HTML manuals from English PDFs under ``_инструкции-pdf/EN/``.

Uses V24 / V230 shells (``TEMPLATES.md``): one voltage per PDF.
Shared layout/render: ``pptx-manual-to-html.py``.

Run from repo root::

    python3 docs/demo/manuals-ru/scripts/en_pdf_to_manuals.py
"""

from __future__ import annotations

import argparse
import html
import sys
import types
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_MANUALS_RU = _SCRIPTS.parent


def _load_manual_html():
    """Load sibling generator as a real module (Python 3.14 dataclasses-safe)."""
    path = _SCRIPTS / "pptx-manual-to-html.py"
    name = "pptx_manual_to_html"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    sys.modules[name] = mod
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, mod.__dict__)
    return mod


mh = _load_manual_html()

WARNINGS_RU = (
    "1. Запрещается использовать электропривод заслонки вне указанной области "
    "применения, особенно в авиационной технике.\n"
    "2. Вскрытие корпуса привода разрешено только производителю. Внутри нет "
    "компонентов, которые пользователь может заменять или ремонтировать.\n"
    "3. Устройство содержит электрические и электронные компоненты, в связи с чем "
    "недопустима утилизация вместе с бытовыми отходами. Необходимо соблюдать все "
    "действующие правила и инструкции, относящиеся к данной конкретной местности."
)

AUX_TABLE = [
    ["Переключатель a", "Клеммы 21, 22", "Клеммы 21, 23"],
    ["0–10°", "Замкнуто", "Разомкнуто"],
    ["10–90°", "Разомкнуто", "Замкнуто"],
    ["Переключатель b", "Клеммы 24, 25", "Клеммы 24, 26"],
    ["0–80°", "Разомкнуто", "Замкнуто"],
    ["80–90°", "Замкнуто", "Разомкнуто"],
]


@dataclass(frozen=True)
class EnPdfSpec:
    """One EN PDF → one RU HTML.

    ``voltage_id``: ``v24`` / ``v230`` (one voltage) or ``dual`` (24+230 in one PDF).
    ``family``: ``mu`` / ``mqu`` (DA) or ``safu`` / ``samu`` (SA).
    """

    stem: str
    pdf_name: str
    title: str
    voltage_id: str  # v24 | v230 | dual
    modulating: bool  # A/AS (DA); unused for SA ON/OFF
    family: str  # mu | mqu | safu | samu
    skus: tuple[str, ...]
    torque: str
    areas: tuple[str, ...]
    running: tuple[str, ...]
    power: str
    sound: str
    mass: str
    shaft: str
    storage_temp: str = "–30…+80 °C"
    ambient_temp: str = "–20…+50 °C"
    ip_rating: str = "IP44"
    shaft_length: str = "≥ 50 мм"
    manual_override: str = "расцепление редуктора кнопкой, с самовозвратом"
    direction: str = "переключателем / клеммами питания"
    # Aux switch b trip angles (SA PDFs: 80° or 85°).
    aux_b_lo: str = "–5…80°"
    aux_b_hi: str = "80…90°"


EN_PDF_SPECS: tuple[EnPdfSpec, ...] = (
    EnPdfSpec(
        stem="da8-16-24-32mu24-a-as",
        pdf_name="da8_16_24_32mu24-a_as.pdf",
        title="DA8/16/24/32MU24 …-A/AS — руководство (RU)",
        voltage_id="v24",
        modulating=True,
        family="mu",
        skus=(
            "DA8MU24-A/AS",
            "DA16MU24-A/AS",
            "DA24MU24-A/AS",
            "DA32MU24-A/AS",
        ),
        torque="8 Нм / 16 Нм / 24 Нм / 32 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²", "< 3,2 м²"),
        running=("< 55 с (95°)", "< 100 с (95°)", "< 160 с (95°)", "< 180 с (95°)"),
        power="4,5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 45 дБ(А)",
        mass="1,2…1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24-32mu24-d-ds",
        pdf_name="da8_16_24_32mu24-d_ds.pdf",
        title="DA8/16/24/32MU24 …-D/DS — руководство (RU)",
        voltage_id="v24",
        modulating=False,
        family="mu",
        skus=(
            "DA8MU24-D/DS",
            "DA16MU24-D/DS",
            "DA24MU24-D/DS",
            "DA32MU24-D/DS",
        ),
        torque="8 Нм / 16 Нм / 24 Нм / 32 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²", "< 3,2 м²"),
        running=("< 55 с (95°)", "< 100 с (95°)", "< 160 с (95°)", "< 180 с (95°)"),
        power="4,5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 45 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24-32mu230-a-as",
        pdf_name="da8_16_24_32mu230-a_as.pdf",
        title="DA8/16/24/32MU230 …-A/AS — руководство (RU)",
        voltage_id="v230",
        modulating=True,
        family="mu",
        skus=(
            "DA8MU230-A/AS",
            "DA16MU230-A/AS",
            "DA24MU230-A/AS",
            "DA32MU230-A/AS",
        ),
        torque="8 Нм / 16 Нм / 24 Нм / 32 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²", "< 3,2 м²"),
        running=("< 55 с (95°)", "< 100 с (95°)", "< 160 с (95°)", "< 180 с (95°)"),
        power="4,5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 45 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24-32mu230-d-ds",
        pdf_name="da8_16_24_32mu230-d_ds.pdf",
        title="DA8/16/24/32MU230 …-D/DS — руководство (RU)",
        voltage_id="v230",
        modulating=False,
        family="mu",
        skus=(
            "DA8MU230-D/DS",
            "DA16MU230-D/DS",
            "DA24MU230-D/DS",
            "DA32MU230-D/DS",
        ),
        torque="8 Нм / 16 Нм / 24 Нм / 32 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²", "< 3,2 м²"),
        running=("< 55 с (95°)", "< 100 с (95°)", "< 160 с (95°)", "< 180 с (95°)"),
        power="4,5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 45 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24mqu24-a-as",
        pdf_name="da8_16_24mqu24-a_as.pdf",
        title="DA8/16/24MQU24 …-A/AS — руководство (RU)",
        voltage_id="v24",
        modulating=True,
        family="mqu",
        skus=("DA8MQU24-A/AS", "DA16MQU24-A/AS", "DA24MQU24-A/AS"),
        torque="8 Нм / 16 Нм / 24 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²"),
        running=("< 8 с (95°)", "< 16 с (95°)", "< 45 с (95°)"),
        power="12 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 55 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24mqu230-a-as",
        pdf_name="da8_16_24mqu230-a_as.pdf",
        title="DA8/16/24MQU230 …-A/AS — руководство (RU)",
        voltage_id="v230",
        modulating=True,
        family="mqu",
        skus=("DA8MQU230-A/AS", "DA16MQU230-A/AS", "DA24MQU230-A/AS"),
        torque="8 Нм / 16 Нм / 24 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²"),
        running=("< 8 с (95°)", "< 16 с (95°)", "< 45 с (95°)"),
        power="12 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 55 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    EnPdfSpec(
        stem="da8-16-24mqu230-d-ds",
        pdf_name="da8_16_24mqu230-d_ds.pdf",
        title="DA8/16/24MQU230 …-D/DS — руководство (RU)",
        voltage_id="v230",
        modulating=False,
        family="mqu",
        skus=("DA8MQU230-D/DS", "DA16MQU230-D/DS", "DA24MQU230-D/DS"),
        torque="8 Нм / 16 Нм / 24 Нм",
        areas=("< 0,8 м²", "< 1,6 м²", "< 2,4 м²"),
        running=("< 8 с (95°)", "< 16 с (95°)", "< 45 с (95°)"),
        power="12 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 55 дБ(А)",
        mass="1,3 кг",
        shaft="круглый 10…20 мм, квадратный 10×10…16×16 мм",
    ),
    # SA FU — fire/smoke spring-return (combined 24+230, DS/DST).
    EnPdfSpec(
        stem="sa3fu-ds-dst",
        pdf_name="sa3fu-ds_dst.pdf",
        title="SA3FU …-DS/DST — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="safu",
        skus=("SA3FU24-DS/DST", "SA3FU230-DS/DST"),
        torque="3 Нм",
        areas=("< 0,3 м²", "< 0,3 м²"),
        running=("< 75 с / < 25 с", "< 75 с / < 25 с"),
        power="5 Вт под нагрузкой\n2 Вт удержание",
        sound=(
            "макс. 45 дБ(А) при работе двигателя, "
            "макс. 50 дБ(А) при возврате пружины"
        ),
        mass="< 1,3 кг",
        shaft="квадратный 12×12 мм (втулки 8×8, 10×10 мм)",
        storage_temp="–40…+70 °C",
        ambient_temp="–20…+50 °C",
        ip_rating="IP54",
        shaft_length="≥ 50 мм",
        manual_override="расцепление редуктора кнопкой, с самовозвратом",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…80°",
        aux_b_hi="80…90°",
    ),
    EnPdfSpec(
        stem="sa5fu-ds-dst",
        pdf_name="sa5fu-ds_dst.pdf",
        title="SA5FU …-DS/DST — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="safu",
        skus=("SA5FU24-DS/DST", "SA5FU230-DS/DST"),
        torque="5 Нм",
        areas=("< 0,5 м²", "< 0,5 м²"),
        running=("< 70 с / < 20 с", "< 70 с / < 20 с"),
        power="5 Вт под нагрузкой\n3 Вт удержание",
        sound=(
            "макс. 45 дБ(А) при работе двигателя, "
            "макс. 62 дБ(А) при возврате пружины"
        ),
        mass="< 1,5 кг",
        shaft="квадратный 12×12 мм (втулки 8×8, 10×10 мм)",
        storage_temp="–40…+70 °C",
        ambient_temp="–20…+50 °C",
        ip_rating="IP54",
        shaft_length="< 90 мм",
        manual_override="расцепление редуктора кнопкой, с самовозвратом",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…80°",
        aux_b_hi="80…90°",
    ),
    EnPdfSpec(
        stem="sa10fu-ds-dst",
        pdf_name="sa10fu-ds_dst.pdf",
        title="SA10FU …-DS/DST — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="safu",
        skus=("SA10FU24-DS/DST", "SA10FU230-DS/DST"),
        torque="10 Нм",
        areas=("< 1,0 м²", "< 1,0 м²"),
        running=("< 100 с / < 25 с", "< 100 с / < 25 с"),
        power="5 Вт под нагрузкой\n3 Вт удержание",
        sound=(
            "макс. 45 дБ(А) при работе двигателя, "
            "макс. 62 дБ(А) при возврате пружины"
        ),
        mass="< 2,5 кг",
        shaft="квадратный 12×12 мм (втулки 8×8, 10×10 мм)",
        storage_temp="–40…+70 °C",
        ambient_temp="–20…+50 °C",
        ip_rating="IP54",
        shaft_length="< 90 мм",
        manual_override="расцепление редуктора кнопкой, с самовозвратом",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…85°",
        aux_b_hi="85…90°",
    ),
    EnPdfSpec(
        stem="sa15fu-ds-dst",
        pdf_name="sa15fu-ds_dst.pdf",
        title="SA15FU …-DS/DST — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="safu",
        skus=("SA15FU24-DS/DST", "SA15FU230-DS/DST"),
        torque="15 Нм",
        areas=("< 1,5 м²", "< 1,5 м²"),
        running=("< 150 с / < 25 с", "< 150 с / < 25 с"),
        power="10 Вт под нагрузкой\n3,5 Вт удержание",
        sound=(
            "макс. 45 дБ(А) при работе двигателя, "
            "макс. 62 дБ(А) при возврате пружины"
        ),
        mass="< 2,8 кг",
        shaft="квадратный 12×12 мм (втулки 8×8, 10×10 мм)",
        storage_temp="–40…+70 °C",
        ambient_temp="–20…+50 °C",
        ip_rating="IP54",
        shaft_length="< 90 мм",
        manual_override="расцепление редуктора кнопкой, с самовозвратом",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…85°",
        aux_b_hi="85…90°",
    ),
    # SA MU — smoke damper, no spring (combined 24+230, только DS — без DST).
    EnPdfSpec(
        stem="sa7mu-ds-dst",
        pdf_name="sa7mu-ds_dst.pdf",
        title="SA7MU …-DS — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="samu",
        skus=("SA7MU24-DS", "SA7MU230-DS"),
        torque="7 Нм",
        areas=("< 0,7 м²", "< 0,7 м²"),
        running=("< 30 с (95°)", "< 30 с (95°)"),
        power="5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 50 дБ(А)",
        mass="1,7 кг",
        shaft="квадратный 12×12 мм",
        storage_temp="–30…+80 °C",
        ambient_temp="–30…+50 °C",
        ip_rating="IP54",
        shaft_length="≥ 50 мм",
        manual_override="металлическая рукоятка",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…80°",
        aux_b_hi="80…90°",
    ),
    EnPdfSpec(
        stem="sa10mu-ds-dst",
        pdf_name="sa10mu-ds_dst.pdf",
        title="SA10MU …-DS — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="samu",
        skus=("SA10MU24-DS", "SA10MU230-DS"),
        torque="10 Нм",
        areas=("< 1,0 м²", "< 1,0 м²"),
        running=("< 45 с (95°)", "< 45 с (95°)"),
        power="5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 50 дБ(А)",
        mass="1,7 кг",
        shaft="квадратный 12×12 мм",
        storage_temp="–30…+80 °C",
        ambient_temp="–30…+50 °C",
        ip_rating="IP54",
        shaft_length="≥ 50 мм",
        manual_override="металлическая рукоятка",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…80°",
        aux_b_hi="80…90°",
    ),
    EnPdfSpec(
        stem="sa15mu-ds-dst",
        pdf_name="sa15mu-ds_dst.pdf",
        title="SA15MU …-DS — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="samu",
        skus=("SA15MU24-DS", "SA15MU230-DS"),
        torque="15 Нм",
        areas=("< 1,5 м²", "< 1,5 м²"),
        running=("< 30 с (95°)", "< 30 с (95°)"),
        power="5 Вт под нагрузкой\n1 Вт удержание",
        sound="макс. 50 дБ(А)",
        mass="1,7 кг",
        shaft="квадратный 12×12 мм",
        storage_temp="–30…+80 °C",
        ambient_temp="–30…+50 °C",
        ip_rating="IP54",
        shaft_length="≥ 90 мм",
        manual_override="металлическая рукоятка",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…80°",
        aux_b_hi="80…90°",
    ),
    EnPdfSpec(
        stem="sa30mu-ds-dst",
        pdf_name="sa30mu-ds_dst.pdf",
        title="SA30MU …-DS — руководство (RU)",
        voltage_id="dual",
        modulating=False,
        family="samu",
        skus=("SA30MU24-DS", "SA30MU230-DS"),
        torque="30 Нм",
        areas=("< 3,0 м²", "< 3,0 м²"),
        running=("< 115 с (95°)", "< 115 с (95°)"),
        power="10 Вт под нагрузкой\n2 Вт удержание",
        sound="макс. 45 дБ(А)",
        mass="2,2 кг",
        shaft="квадратный 12×12 мм",
        storage_temp="–30…+80 °C",
        ambient_temp="–30…+50 °C",
        ip_rating="IP54",
        shaft_length="≥ 90 мм",
        manual_override="металлическая рукоятка",
        direction="для монтажа с противоположной стороны",
        aux_b_lo="–5…85°",
        aux_b_hi="85…90°",
    ),
)


def _sa_aux_table(spec: EnPdfSpec) -> list[list[str]]:
    """Factory aux angles — cable terminals S1–S6 (EN SA PDFs)."""
    return [
        ["Переключатель a", "Клеммы S1, S2", "Клеммы S1, S3"],
        ["–5…5°", "Замкнуто", "Разомкнуто"],
        ["5…90°", "Разомкнуто", "Замкнуто"],
        ["Переключатель b", "Клеммы S4, S5", "Клеммы S4, S6"],
        [spec.aux_b_lo, "Замкнуто", "Разомкнуто"],
        [spec.aux_b_hi, "Разомкнуто", "Замкнуто"],
    ]


def _build_doc(spec: EnPdfSpec):
    n = len(spec.skus)
    assert len(spec.areas) == n and len(spec.running) == n
    is_sa = spec.family in {"safu", "samu"}

    if is_sa:
        if spec.family == "safu":
            edition = (
                "Исполнения «DS» / «DST» включают 2 группы вспомогательных "
                "переключателей."
            )
            dst_note = "Исполнение «DST» — с термодатчиком SAF72."
        else:
            # SAMU EN PDFs: только DS (без DST / SAF72).
            edition = (
                "Исполнение «DS» включает 2 группы вспомогательных переключателей."
            )
            dst_note = ""
        direction = spec.direction
        angle = "Макс. 95°"
        if spec.family == "safu":
            # Глоссарий Belimo RU / series-card: противопожарный клапан (не «пружинный»).
            heading = (
                "Привод противопожарного клапана — 2-позиционное управление"
            )
            intro = (
                "Для противопожарных и дымовых клапанов в системах HVAC "
                "(отопления, вентиляции и кондиционирования воздуха)"
            )
            control = "Управление: вкл./выкл. (ON/OFF)"
            doc_title = (
                "Руководство по эксплуатации — привод противопожарного клапана"
            )
            running_label = "Время поворота / возврат пружины"
        else:
            heading = "2- / 3-позиционное управление"
            intro = (
                "Для управления дымовыми клапанами в системах дымоудаления "
                "и противодымной вентиляции"
            )
            control = "Управление: 2- / 3-позиционное"
            doc_title = (
                "Руководство по эксплуатации — привод дымового клапана"
            )
            running_label = "Время поворота"
        lead_voltage = (
            "Номинальное напряжение: AC/DC 24 В; AC 100…240 В"
        )
        summary_lines = [
            heading,
            intro,
            f"Крутящий момент: {spec.torque}",
            f"{running_label}: {spec.running[0]}",
            lead_voltage,
            control,
            edition,
        ]
        if dst_note:
            summary_lines.append(dst_note)
        summary = "\n".join(summary_lines)
        elec = [
            [
                "Номинальное напряжение",
                "AC/DC 24 В, 50/60 Гц",
                "AC 100…240 В, 50/60 Гц",
            ],
            ["Потребляемая мощность", spec.power, spec.power],
            ["Сечение подключаемых проводов", "0,5 мм²", "0,5 мм²"],
        ]
        aux_table = _sa_aux_table(spec)
    elif spec.modulating:
        vt = mh.VOLTAGE_TEMPLATES[spec.voltage_id]
        control = (
            "Упр. сигнал Y: 0(2)…10 В= / 0(4)…20 мА (спецзаказ)\n"
            "Обратная связь U: 0(2)…10 В= / 0(4)…20 мА (спецзаказ)"
        )
        edition = (
            "Исполнение «AS» включает 2 группы вспомогательных переключателей."
        )
        direction = "изменением DIP-переключателей"
        angle = "Макс. 95°, настраивается механическими упорами"
        heading = (
            "Пропорциональное управление"
            if spec.family == "mu"
            else "Привод ускоренного срабатывания — пропорциональное управление"
        )
        summary = "\n".join(
            [
                heading,
                "Для управления воздушными заслонками в системах HVAC "
                "(отопления, вентиляции и кондиционирования воздуха)",
                f"Крутящий момент: {spec.torque}",
                f"Время поворота: {', '.join(spec.running)}",
                vt.lead_voltage,
                control,
                edition,
            ]
        )
        elec = [
            ["Номинальное напряжение", vt.nominal_voltage],
            ["Потребляемая мощность", spec.power],
            ["Сечение подключаемых проводов", "0,5 мм²"],
        ]
        aux_table = list(AUX_TABLE)
        if spec.family == "mqu":
            doc_title = (
                "Руководство по эксплуатации — привод ускоренного срабатывания"
            )
        else:
            doc_title = "Руководство по эксплуатации — пропорциональный привод"
    else:
        vt = mh.VOLTAGE_TEMPLATES[spec.voltage_id]
        control = "Управление: 2- / 3-позиционное"
        edition = (
            "Исполнение «DS» включает 2 группы вспомогательных переключателей."
        )
        direction = "переключателем / клеммами питания"
        angle = "Макс. 95°"
        heading = (
            "2- / 3-позиционное управление"
            if spec.family == "mu"
            else "Привод ускоренного срабатывания — 2- / 3-позиционное управление"
        )
        summary = "\n".join(
            [
                heading,
                "Для управления воздушными заслонками в системах HVAC "
                "(отопления, вентиляции и кондиционирования воздуха)",
                f"Крутящий момент: {spec.torque}",
                f"Время поворота: {', '.join(spec.running)}",
                vt.lead_voltage,
                control,
                edition,
            ]
        )
        elec = [
            ["Номинальное напряжение", vt.nominal_voltage],
            ["Потребляемая мощность", spec.power],
            ["Сечение подключаемых проводов", "0,5 мм²"],
        ]
        aux_table = list(AUX_TABLE)
        if spec.family == "mqu":
            doc_title = (
                "Руководство по эксплуатации — привод ускоренного срабатывания"
            )
        else:
            doc_title = "Руководство по эксплуатации — привод вкл./выкл."

    time_row = (
        "Время поворота / возврат пружины"
        if spec.family == "safu"
        else "Время поворота"
    )
    func = [
        ["Функциональные параметры", *([""] * n)],
        ["Площадь обслуживаемой заслонки", *spec.areas],
        [time_row, *spec.running],
        ["Направление вращения", *([direction] * n)],
        ["Ручное управление", *([spec.manual_override] * n)],
        ["Угол поворота", *([angle] * n)],
        ["Уровень звуковой мощности", *([spec.sound] * n)],
        ["Индикация положения", *(["Механический указатель"] * n)],
        ["Условия эксплуатации", *([""] * n)],
        [
            "Класс защиты",
            *(
                [mh._protection_class_for_sku(s) for s in spec.skus]
                if is_sa
                else [mh.VOLTAGE_TEMPLATES[spec.voltage_id].protection_class] * n
            ),
        ],
        ["Степень защиты корпуса", *([spec.ip_rating] * n)],
        ["Температура окружающей среды", *([spec.ambient_temp] * n)],
        ["Температура хранения", *([spec.storage_temp] * n)],
        [
            "Испытание на влажность",
            *(["5…95 % относительной влажности, без конденсата / EN 60730-1"] * n),
        ],
        ["Габаритные размеры / Масса", *([""] * n)],
        [
            "Габаритные размеры (Д × Ш × В)",
            *(["См. «Габаритные размеры»"] * n),
        ],
        ["Длина вала заслонки", *([spec.shaft_length] * n)],
        ["Диаметр вала заслонки", *([spec.shaft] * n)],
        ["Масса", *([spec.mass] * n)],
    ]

    return mh.ManualDoc(
        stem=spec.stem,
        title=spec.title,
        doc_title=doc_title,
        torque=spec.torque,
        skus=list(spec.skus),
        warnings=WARNINGS_RU,
        summary=summary,
        electrical_table=elec,
        function_table=func,
        aux_table=aux_table,
        product_photo="product.png",
        lead_photo="lead.png",
    )


def convert_en_pdf(spec: EnPdfSpec, out_dir: Path, *, force: bool = False) -> Path:
    """Materialize assets from EN PDF and write ``{DA,SA,HV}/{stem}.html``."""
    finished_dir = mh.finished_manuals_dir(out_dir, stem=spec.stem)
    finished_dir.mkdir(parents=True, exist_ok=True)
    mh._ensure_family_logo(finished_dir)
    html_path = finished_dir / f"{spec.stem}.html"
    if mh.manual_stem_is_locked(spec.stem) and not force:
        if html_path.is_file():
            return html_path
        raise FileNotFoundError(
            f"Locked manual {spec.stem!r} has no HTML yet; use --force to build."
        )

    assets = finished_dir / "assets" / spec.stem
    if assets.exists():
        for old in assets.iterdir():
            if old.is_file():
                old.unlink()
    assets.mkdir(parents=True, exist_ok=True)

    profile = mh.ensure_diagram_assets(spec.stem, finished_dir, force=force)
    doc = _build_doc(spec)
    if (assets / "product.png").is_file():
        doc.product_photo = "product.png"
        doc.lead_photo = (
            "lead.png" if (assets / "lead.png").is_file() else "product.png"
        )
    body = mh.render_grid(doc, diagram_profile=profile)
    if spec.voltage_id == "dual":
        note = (
            '<p class="template-voltage-note"><strong>'
            "AC/DC 24 В + AC 100…240 В</strong>"
            f" — перевод с EN PDF <code>{html.escape(spec.pdf_name)}</code> "
            "(оба напряжения в одном руководстве). "
            "Канон: <code>TEMPLATES.md</code>.</p>"
        )
    else:
        note = (
            f'<p class="template-voltage-note"><strong>'
            f"{html.escape(mh.VOLTAGE_TEMPLATES[spec.voltage_id].label_ru)}</strong>"
            f" — перевод с EN PDF <code>{html.escape(spec.pdf_name)}</code>. "
            f"Шаблон {html.escape(spec.voltage_id.upper())}; "
            f"канон: <code>TEMPLATES.md</code>.</p>"
        )
    body = body.replace(
        '<section class="sheet sheet-page1">',
        f'{note}<section class="sheet sheet-page1">',
        1,
    )
    html_path.write_text(
        mh.HTML_SHELL.format(title=html.escape(spec.title), body=body),
        encoding="utf-8",
    )
    return html_path


def rewrite_index(out_dir: Path, en_rows: list[tuple[str, str]]) -> None:
    """Refresh index.html including EN→RU stems and voltage templates."""
    title_by_stem = {stem: title for stem, title in mh.STEM_MAP.values()}
    for stem, title in en_rows:
        title_by_stem[stem] = title
    rows: list[str] = [
        "<li><strong>Шаблоны напряжения (для EN→RU)</strong><br>"
        '<a href="template-v24.html">V24 — AC/DC 24 В</a> · '
        '<a href="template-v230.html">V230 — AC 100…240 В</a> · '
        "<code>TEMPLATES.md</code></li>",
        "<li><strong>Семейства готовых руководств</strong><br>"
        '<code>DA/</code> (готово) · <code>SA/</code> (готово) · '
        '<code>HV/</code> (очередь EN)</li>',
    ]
    by_family: dict[str, list[tuple[str, str]]] = {
        "DA": [],
        "SA": [],
        "HV": [],
    }
    listed: set[str] = set()
    for fam_dir, stem, _path in mh.iter_finished_manual_html(out_dir):
        listed.add(stem)
        by_family.setdefault(fam_dir, []).append(
            (stem, title_by_stem.get(stem, stem)),
        )
    for stem, title in en_rows:
        if stem in listed:
            continue
        fam = mh.finished_manuals_subdir(stem)
        by_family.setdefault(fam, []).append((stem, title))
        listed.add(stem)
    for fam in ("DA", "SA", "HV"):
        items = by_family.get(fam) or []
        if not items and fam != "DA":
            rows.append(
                f"<li><strong>{fam}/</strong> — папка готова, HTML пока нет "
                f"(EN PDF в <code>_инструкции-pdf/EN/</code>)</li>",
            )
            continue
        rows.append(f"<li><strong>{fam}/</strong><ul>")
        for stem, title in sorted(items, key=lambda x: x[0]):
            rows.append(
                f"<li><strong>{html.escape(title)}</strong><br>"
                f'<a href="{fam}/{stem}.html">HTML (сетка 12 / A4)</a></li>',
            )
        rows.append("</ul></li>")
    (out_dir / "index.html").write_text(
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Инструкции SKU (RU)</title>"
        "<style>body{font-family:system-ui;max-width:820px;margin:2rem auto;"
        "padding:0 1rem}li{margin:.65rem 0}</style></head><body>"
        "<h1>Руководства по эксплуатации (RU)</h1>"
        "<p>Адаптивная вёрстка на 12 колонках, 2 листа A4 альбом. "
        "Готовые руководства — в <code>DA/</code>, <code>SA/</code>, "
        "<code>HV/</code>. "
        "Новые переводы с EN — шаблоны "
        "<a href='template-v24.html'>V24</a> / "
        "<a href='template-v230.html'>V230</a>.</p>"
        f"<ol>{''.join(rows)}</ol></body></html>\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=_MANUALS_RU)
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional stem filter (default: all EN_PDF_SPECS).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even LOCKED_MANUAL_STEMS (finished manuals).",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for path in mh.write_voltage_template_shells(args.out_dir):
        print("OK", path.name)

    only = set(args.only) if args.only else None
    en_rows: list[tuple[str, str]] = [(s.stem, s.title) for s in EN_PDF_SPECS]
    for spec in EN_PDF_SPECS:
        if only is not None and spec.stem not in only:
            continue
        locked = mh.manual_stem_is_locked(spec.stem) and not args.force
        try:
            out = convert_en_pdf(spec, args.out_dir, force=args.force)
        except FileNotFoundError as exc:
            print("SKIP", spec.stem, exc)
            continue
        if locked:
            print("LOCKED", out.name, "(не пересобран)")
        else:
            print("OK", out.name, "←", spec.pdf_name)

    rewrite_index(args.out_dir, en_rows)
    print("OK index.html")


if __name__ == "__main__":
    main()
