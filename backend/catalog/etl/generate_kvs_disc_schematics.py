"""Build gallery tiles for brass 8100 characterizing discs from port photos.

Canon: circular photo of the orifice **as-is**, white background, same title
block as the old SVG tiles. Drop source shots into ``src/dn{DN}-{letter}.png``
(or ``.jpg`` / ``.webp``), then regenerate.

Usage::

    # add photos → backend/catalog/etl/data/ball-valve-kvs-discs/src/dn15-a.png …
    poetry run python -m catalog.etl.generate_kvs_disc_schematics
    poetry run python manage.py attach_ball_valve_kvs_discs
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from catalog.etl.webp import convert_bytes_to_webp

_PACK_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "ball-valve-kvs-discs"
_SRC_DIR: Final[Path] = _PACK_DIR / "src"
_SIZE: Final[int] = 900
_BG: Final[str] = "#ffffff"
_PHOTO_SCALE: Final[float] = 0.76
_PHOTO_Y_BIAS: Final[int] = 20  # leave room for title

_KVS: Final[dict[tuple[int, str], float]] = {
    (15, "a"): 1.6,
    (15, "b"): 2.5,
    (15, "c"): 4.0,
    (15, "d"): 6.3,
    (15, "e"): 10.1,
    (20, "a"): 1.6,
    (20, "b"): 2.5,
    (20, "c"): 4.0,
    (20, "d"): 6.3,
    (20, "e"): 10.1,
    (25, "a"): 10.0,
    (25, "b"): 16.0,
    (32, "a"): 16.0,
    (32, "b"): 25.0,
    (40, "a"): 25.0,
    (40, "b"): 40.0,
    (50, "a"): 40.0,
    (50, "b"): 63.0,
}

_FONT_CANDIDATES: Final[tuple[str, ...]] = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

_SRC_SUFFIXES: Final[tuple[str, ...]] = (".png", ".jpg", ".jpeg", ".webp")


def _fmt_kvs(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    if text.endswith(",0"):
        return text[:-2]
    return text


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def find_src_photo(*, dn: int, letter: str, src_dir: Path | None = None) -> Path | None:
    """Return ``src/dn{{DN}}-{{letter}}.(png|jpg|webp)`` if present."""
    root = src_dir or _SRC_DIR
    stem = f"dn{dn}-{letter.casefold()}"
    for suffix in _SRC_SUFFIXES:
        path = root / f"{stem}{suffix}"
        if path.is_file():
            return path
    return None


def compose_disc_photo_tile(
    photo: Image.Image,
    *,
    dn: int,
    letter: str,
    size: int = _SIZE,
) -> Image.Image:
    """White square + circular port photo + SVG-style labels."""
    kvs = _fmt_kvs(_KVS[(dn, letter.casefold())])
    diameter = max(64, int(size * _PHOTO_SCALE))
    rgba = photo.convert("RGBA")
    rgba = rgba.resize((diameter, diameter), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (size, size), _BG)
    ox = (size - diameter) // 2
    oy = (size - diameter) // 2 + _PHOTO_Y_BIAS
    if rgba.getchannel("A").getextrema() != (255, 255):
        canvas.paste(rgba, (ox, oy), rgba)
    else:
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
        canvas.paste(rgba.convert("RGB"), (ox, oy), mask)

    draw = ImageDraw.Draw(canvas)
    title = f"Расходный диск · исполнение {letter.upper()}"
    subtitle = f"DN {dn} · Kvs {kvs} м³/ч"
    note = f"Фото отверстия (DN{dn} · Kvs {kvs})"
    draw.text((size / 2, 28), title, fill="#1a1a1a", font=_font(28), anchor="mt")
    draw.text((size / 2, 62), subtitle, fill="#555555", font=_font(22), anchor="mt")
    draw.text((size / 2, size - 40), note, fill="#777777", font=_font(16), anchor="mt")
    return canvas


def generate_kvs_disc_schematics(*, pack_dir: Path | None = None) -> dict[str, str]:
    """Compose WebP tiles for every ``src/dn*-*.png`` photo present."""
    root = pack_dir or _PACK_DIR
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    summary: dict[str, str] = {}
    for (dn, letter), _kvs in sorted(_KVS.items()):
        stem = f"dn{dn}-{letter}"
        photo_path = find_src_photo(dn=dn, letter=letter, src_dir=src)
        if photo_path is None:
            summary[stem] = "skip: no src photo"
            continue
        tile = compose_disc_photo_tile(Image.open(photo_path), dn=dn, letter=letter)
        buf = BytesIO()
        tile.save(buf, format="PNG")
        webp = convert_bytes_to_webp(buf.getvalue())
        webp_path = root / f"{stem}.webp"
        webp_path.write_bytes(webp)
        svg_path = root / f"{stem}.svg"
        if svg_path.is_file():
            svg_path.unlink()
        summary[stem] = f"webp={webp_path.stat().st_size} from={photo_path.name}"
    return summary


def main() -> None:
    """CLI entry."""
    result = generate_kvs_disc_schematics()
    for key, info in result.items():
        print(f"{key}: {info}")
    done = sum(1 for info in result.values() if info.startswith("webp="))
    print(f"composed {done}/{len(result)} photo tiles → {_PACK_DIR}")


if __name__ == "__main__":
    main()
