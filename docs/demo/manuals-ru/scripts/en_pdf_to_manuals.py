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
    """One EN PDF → one RU HTML (single voltage)."""

    stem: str
    pdf_name: str
    title: str
    voltage_id: str  # v24 | v230
    modulating: bool  # A/AS
    family: str  # mu | mqu
    skus: tuple[str, ...]
    torque: str
    areas: tuple[str, ...]
    running: tuple[str, ...]
    power: str
    sound: str
    mass: str
    shaft: str
    storage_temp: str = "–30…+80 °C"


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
)


def _build_doc(spec: EnPdfSpec):
    vt = mh.VOLTAGE_TEMPLATES[spec.voltage_id]
    n = len(spec.skus)
    assert len(spec.areas) == n and len(spec.running) == n

    if spec.modulating:
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
            else "Быстроходный привод — пропорциональное управление"
        )
    else:
        control = "Управление: 2-позиционное и 3-позиционное"
        edition = (
            "Исполнение «DS» включает 2 группы вспомогательных переключателей."
        )
        direction = "переключателем / клеммами питания"
        angle = "Макс. 95°"
        heading = (
            "2-позиционное и 3-позиционное управление"
            if spec.family == "mu"
            else "Быстроходный привод — 2-/3-позиционное управление"
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
    func = [
        ["Функциональные параметры", *([""] * n)],
        ["Площадь обслуживаемой заслонки", *spec.areas],
        ["Время поворота", *spec.running],
        ["Направление вращения", *([direction] * n)],
        [
            "Ручное управление",
            *(["расцепление редуктора кнопкой, с самовозвратом"] * n),
        ],
        ["Угол поворота", *([angle] * n)],
        ["Уровень звуковой мощности", *([spec.sound] * n)],
        ["Индикация положения", *(["Механический указатель"] * n)],
        ["Условия эксплуатации", *([""] * n)],
        ["Класс защиты", *([vt.protection_class] * n)],
        ["Степень защиты корпуса", *(["IP44"] * n)],
        ["Температура окружающей среды", *(["–20…+50 °C"] * n)],
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
        ["Длина вала заслонки", *(["≥ 50 мм"] * n)],
        ["Диаметр вала заслонки", *([spec.shaft] * n)],
        ["Масса", *([spec.mass] * n)],
    ]

    if spec.family == "mqu":
        doc_title = "Руководство по эксплуатации — быстроходный привод"
    elif spec.modulating:
        doc_title = "Руководство по эксплуатации — пропорциональный привод"
    else:
        doc_title = "Руководство по эксплуатации — привод вкл./выкл."

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
        aux_table=list(AUX_TABLE),
        product_photo="product.png",
        lead_photo="lead.png",
    )


def convert_en_pdf(spec: EnPdfSpec, out_dir: Path) -> Path:
    """Materialize assets from EN PDF and write ``{stem}.html``."""
    assets = out_dir / "assets" / spec.stem
    if assets.exists():
        for old in assets.iterdir():
            if old.is_file():
                old.unlink()
    assets.mkdir(parents=True, exist_ok=True)

    profile = mh.ensure_diagram_assets(spec.stem, out_dir)
    doc = _build_doc(spec)
    if (assets / "product.png").is_file():
        doc.product_photo = "product.png"
        doc.lead_photo = (
            "lead.png" if (assets / "lead.png").is_file() else "product.png"
        )
    body = mh.render_grid(doc, diagram_profile=profile)
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
    html_path = out_dir / f"{spec.stem}.html"
    html_path.write_text(
        mh.HTML_SHELL.format(title=html.escape(spec.title), body=body),
        encoding="utf-8",
    )
    return html_path


def rewrite_index(out_dir: Path, en_rows: list[tuple[str, str]]) -> None:
    """Refresh index.html including EN→RU stems and voltage templates."""
    rows: list[str] = [
        "<li><strong>Шаблоны напряжения (для EN→RU)</strong><br>"
        '<a href="template-v24.html">V24 — AC/DC 24 В</a> · '
        '<a href="template-v230.html">V230 — AC 100…240 В</a> · '
        "<code>TEMPLATES.md</code></li>",
        "<li><strong>EN→RU (раздельные PDF 24 / 230 В)</strong><ul>",
    ]
    for stem, title in en_rows:
        rows.append(
            f"<li><strong>{html.escape(title)}</strong><br>"
            f'<a href="{stem}.html">HTML (сетка 12 / A4)</a></li>',
        )
    rows.append("</ul></li>")
    for stem, title in sorted(mh.STEM_MAP.values(), key=lambda x: x[0]):
        if (out_dir / f"{stem}.html").is_file():
            rows.append(
                f"<li><strong>{html.escape(title)}</strong><br>"
                f'<a href="{stem}.html">HTML (сетка 12 / A4)</a></li>',
            )
    (out_dir / "index.html").write_text(
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Инструкции SKU (RU)</title>"
        "<style>body{font-family:system-ui;max-width:820px;margin:2rem auto;"
        "padding:0 1rem}li{margin:.65rem 0}</style></head><body>"
        "<h1>Руководства по эксплуатации (RU)</h1>"
        "<p>Адаптивная вёрстка на 12 колонках, 2 листа A4 альбом. "
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
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for path in mh.write_voltage_template_shells(args.out_dir):
        print("OK", path.name)

    only = set(args.only) if args.only else None
    en_rows: list[tuple[str, str]] = []
    for spec in EN_PDF_SPECS:
        if only is not None and spec.stem not in only:
            continue
        try:
            out = convert_en_pdf(spec, args.out_dir)
        except FileNotFoundError as exc:
            print("SKIP", spec.stem, exc)
            continue
        print("OK", out.name, "←", spec.pdf_name)
        en_rows.append((spec.stem, spec.title))

    rewrite_index(args.out_dir, en_rows)
    print("OK index.html")


if __name__ == "__main__":
    main()
