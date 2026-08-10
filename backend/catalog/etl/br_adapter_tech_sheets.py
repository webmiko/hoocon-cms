"""Rebuild BR-M / BR-ML adapter tech PDFs with Russian titles (not Chinese plant sheets).

Source geometry is taken from the existing Disk PDFs under ``_инструкции-pdf/RU/``;
Chinese requirement / title-block text is replaced with Hoocon RU copy. Dimensions
stay as on the drawing.

Usage::

    poetry run python -m catalog.etl.br_adapter_tech_sheets
    poetry run python manage.py attach_manual_pdfs --series br
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _default_manuals_dir() -> Path:
    """``_инструкции-pdf`` next to repo root (no Django import)."""
    return Path(__file__).resolve().parents[3] / "_инструкции-pdf"


_A4_PX: Final[tuple[int, int]] = (1191, 1684)  # ~2× 595×842 pt
_MARGIN: Final[int] = 48
_FONT_CANDIDATES: Final[tuple[str, ...]] = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


@dataclass(frozen=True, slots=True)
class BrTechSheetSpec:
    """One adapter tech PDF to rebuild."""

    disk_names: tuple[str, ...]  # NFC basenames under RU/ (output target)
    out_name: str
    zh_png: str  # committed OEM render under tech-zh/
    title: str
    subtitle: str
    drawing_no: str
    length_note: str
    tech_lines: tuple[str, ...]
    bom_lines: tuple[str, ...]
    # Crop of geometry from the OEM render (x0,y0,x1,y1) at 2× A4.
    geometry_box: tuple[int, int, int, int]


_COMMON_TECH: Final[tuple[str, ...]] = (
    "Клёпка надёжная, без люфта.",
    "Острые кромки притупить; неуказанные фаски 0,5×45°.",
    "Покрытие поверхности: белое цинкование.",
    "Неуказанные допуски формы и расположения — по GB/T 1184-k.",
    "Неуказанные линейные отклонения — по GB/T 1804-m.",
)

_SPECS: Final[tuple[BrTechSheetSpec, ...]] = (
    BrTechSheetSpec(
        disk_names=("Техничка на кронштейн.pdf",),
        out_name="Техничка на кронштейн.pdf",
        zh_png="kronshteyn-zh.png",
        title="Кронштейн (адаптер) Hoocon BR-M / BR-ML",
        subtitle="Габаритный чертёж посадочной площадки под привод",
        drawing_no="BR-BRACKET",
        length_note="Общая длина ≈ 181 мм; ширина ≈ 70 мм; высота ≈ 68,2 мм.",
        tech_lines=(
            "Кронштейн общий для BR-M и BR-ML (посадочные отверстия 4×Ø5,2).",
            "Перед монтажом сверить отверстие штока с комплектом BR-M или BR-ML.",
            "Размеры на чертеже — в миллиметрах.",
        ),
        bom_lines=(
            "1. Корпус кронштейна — 1 шт.",
            "Крепёж к приводу / крану — по комплектации.",
        ),
        geometry_box=(80, 40, 1100, 1500),
    ),
    BrTechSheetSpec(
        disk_names=("Техничка штока BR-M.pdf", "техничка штока BR-M.pdf"),
        out_name="Техничка штока BR-M.pdf",
        zh_png="shtok-br-m-zh.png",
        title="Соединительный шток Hoocon BR-M",
        subtitle="Для приводов без возвратной пружины (MU / MQU)",
        drawing_no="HC-DA04-901-1",
        length_note="Длина штока 128 мм; головка Ø22×58; квадрат привода 12×12; хвостовик 9×9; резьба M4.",
        tech_lines=_COMMON_TECH,
        bom_lines=(
            "1. Круглая головка Ø22×58 — сталь 45 — 1 шт.",
            "2. Квадратный хвостовик 12×12×85 — сталь 45 — 1 шт.",
        ),
        geometry_box=(160, 15, 1000, 1540),
    ),
    BrTechSheetSpec(
        disk_names=("Техничка штока BR-ML.pdf", "техничка штока BR-ML.pdf"),
        out_name="Техничка штока BR-ML.pdf",
        zh_png="shtok-br-ml-zh.png",
        title="Соединительный шток Hoocon BR-ML",
        subtitle="Для приводов с возвратной пружиной (FU); удлинённый (+35)",
        drawing_no="HC-DAS05-901-1",
        length_note="Длина штока 163 мм; головка Ø22×58; квадрат привода 12×12; хвостовик 9×9; резьба M4.",
        tech_lines=_COMMON_TECH,
        bom_lines=(
            "1. Круглая головка Ø22×58 — сталь 45 — 1 шт.",
            "2. Квадратный хвостовик 12×12×120 — сталь 45 — 1 шт.",
        ),
        geometry_box=(160, 15, 1000, 1540),
    ),
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _nfc_name(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _find_dest_pdf(manuals_ru: Path, names: tuple[str, ...], out_name: str) -> Path:
    """Resolve output path under RU/ (reuse NFD name if present)."""
    wanted = {_nfc_name(n).casefold() for n in names}
    if manuals_ru.is_dir():
        for path in manuals_ru.glob("*.pdf"):
            if _nfc_name(path.name).casefold() in wanted:
                return path
    return manuals_ru / out_name


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for word in words[1:]:
        trial = f"{cur} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def _tech_zh_dir() -> Path:
    """Committed OEM renders used as geometry source (Chinese text blanked)."""
    return Path(__file__).resolve().parent / "data" / "adapters-br" / "tech-zh"


def _blank_chinese_panels(page: Image.Image, *, kind: str) -> Image.Image:
    """Cover OEM Chinese requirement / title-block panels on the rendered page."""
    img = page.copy()
    draw = ImageDraw.Draw(img)
    # Approximate panels at 2× A4 render (1191×1684).
    if kind == "stem":
        # Chinese «技术要求» under top view — keep stem body clear.
        draw.rectangle((30, 260, 400, 500), fill="white")
        # Far-left revision stamps only (do not wipe dimension callouts).
        draw.rectangle((15, 20, 130, 1540), fill="white")
        # Small OEM parts table (vertical) left of the shaft — keep geometry.
        draw.rectangle((130, 620, 270, 1180), fill="white")
        # Title block / plant BOM (bottom-right); leave lower stem tip visible.
        draw.rectangle((560, 1380, 1185, 1670), fill="white")
        draw.rectangle((15, 1580, 560, 1670), fill="white")
        # Right margin noise.
        draw.rectangle((1020, 200, 1185, 1380), fill="white")
    elif kind == "bracket":
        draw.rectangle((20, 1500, 1180, 1665), fill="white")
        draw.rectangle((20, 30, 180, 1500), fill="white")
    return img


def build_ru_sheet(spec: BrTechSheetSpec, source_page: Image.Image) -> Image.Image:
    """Compose an A4 RU tech sheet: header + geometry crop + requirements."""
    kind = "bracket" if "кронштейн" in spec.title.casefold() else "stem"
    cleaned = _blank_chinese_panels(source_page, kind=kind)

    page = Image.new("RGB", _A4_PX, "white")
    draw = ImageDraw.Draw(page)
    font_title = _font(28)
    font_sub = _font(18)
    font_body = _font(16)
    font_small = _font(14)

    y = _MARGIN
    draw.text((_MARGIN, y), "hoocon.ru", fill=(180, 30, 30), font=font_sub)
    y += 28
    draw.text((_MARGIN, y), spec.title, fill=(20, 20, 20), font=font_title)
    y += 36
    for line in _wrap(draw, spec.subtitle, font_sub, _A4_PX[0] - 2 * _MARGIN):
        draw.text((_MARGIN, y), line, fill=(60, 60, 60), font=font_sub)
        y += 24
    draw.text(
        (_MARGIN, y),
        f"Чертёж {spec.drawing_no} · масштаб 1:1 · размеры в мм",
        fill=(90, 90, 90),
        font=font_small,
    )
    y += 28
    for line in _wrap(draw, spec.length_note, font_body, _A4_PX[0] - 2 * _MARGIN):
        draw.text((_MARGIN, y), line, fill=(30, 30, 30), font=font_body)
        y += 22
    y += 8
    draw.line((_MARGIN, y, _A4_PX[0] - _MARGIN, y), fill=(200, 200, 200), width=2)
    y += 12

    geom = cleaned.crop(spec.geometry_box)
    max_w = _A4_PX[0] - 2 * _MARGIN
    # Leave room for RU requirements under a full-length stem drawing.
    max_h = 1020
    gw, gh = geom.size
    scale = min(max_w / gw, max_h / gh, 1.0)
    if scale < 1.0:
        geom = geom.resize((int(gw * scale), int(gh * scale)), Image.Resampling.LANCZOS)
    page.paste(geom, (_MARGIN, y))
    y += geom.size[1] + 16

    draw.text((_MARGIN, y), "Технические требования", fill=(20, 20, 20), font=font_sub)
    y += 26
    for i, raw in enumerate(spec.tech_lines, start=1):
        numbered = f"{i}. {raw}"
        for line in _wrap(draw, numbered, font_body, max_w):
            draw.text((_MARGIN, y), line, fill=(30, 30, 30), font=font_body)
            y += 20
        y += 4

    y += 6
    draw.text((_MARGIN, y), "Состав", fill=(20, 20, 20), font=font_sub)
    y += 26
    for raw in spec.bom_lines:
        for line in _wrap(draw, raw, font_body, max_w):
            draw.text((_MARGIN, y), line, fill=(30, 30, 30), font=font_body)
            y += 20

    footer = "Hoocon · техническая документация · перевод габаритов OEM"
    draw.text((_MARGIN, _A4_PX[1] - _MARGIN), footer, fill=(120, 120, 120), font=font_small)
    return page


def sheet_to_pdf_bytes(sheet: Image.Image) -> bytes:
    """Encode one RGB page as a single-page PDF."""
    buf = BytesIO()
    # Pillow PDF expects RGB; dpi keeps print size near A4.
    sheet.save(buf, format="PDF", resolution=144.0)
    return buf.getvalue()


def rebuild_br_adapter_tech_pdfs(
    *,
    manuals_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    """Rewrite RU tech PDFs on Disk path; return ``{out_name: status}``."""
    root = manuals_dir or _default_manuals_dir()
    ru = root / "RU"
    summary: dict[str, str] = {}
    if not ru.is_dir():
        return {"error": f"missing {ru}"}

    zh_dir = _tech_zh_dir()
    for spec in _SPECS:
        zh_path = zh_dir / spec.zh_png
        if not zh_path.is_file():
            summary[spec.out_name] = f"zh_missing:{spec.zh_png}"
            logger.warning("BR tech ZH source missing: %s", zh_path)
            continue
        page = Image.open(zh_path).convert("RGB")
        sheet = build_ru_sheet(spec, page)
        payload = sheet_to_pdf_bytes(sheet)
        dest = _find_dest_pdf(ru, spec.disk_names, spec.out_name)
        if dry_run:
            summary[spec.out_name] = f"would_write:{len(payload)}"
            continue
        dest.write_bytes(payload)
        summary[spec.out_name] = f"written:{len(payload)}->{dest.name}"
        logger.info("BR tech RU written %s (%s bytes)", dest, len(payload))
    return summary


def main() -> None:
    """CLI entry: ``python -m catalog.etl.br_adapter_tech_sheets``."""
    logging.basicConfig(level=logging.INFO)
    summary = rebuild_br_adapter_tech_pdfs()
    logger.info("BR tech rebuild done: %s", summary)


if __name__ == "__main__":
    main()
