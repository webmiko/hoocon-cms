"""Compose the 3-way 8100 flow-direction gallery tile.

Source of truth: plant sheet «Направление потоков для шаровых кранов»
(4 mounting states × extremes 0° / 90°). Word embeds only tiny icon
fragments — we redraw a clean full-page schematic for the PDP gallery.

Usage::

    poetry run python -m catalog.etl.generate_ball_valve_flow_scheme
    poetry run python manage.py attach_ball_valve_flow_scheme
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from catalog.etl.webp import convert_bytes_to_webp

_PACK_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "ball-valve-flow-scheme"
_OUT_NAME: Final[str] = "flow-3way.webp"
_W: Final[int] = 1600
_H: Final[int] = 1100
_BG: Final[str] = "#ffffff"
_INK: Final[str] = "#1a1a1a"
_MUTED: Final[str] = "#555555"
_GRID: Final[str] = "#d0d0d0"

_FONT_CANDIDATES: Final[tuple[str, ...]] = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

# Four mounting states from the plant sheet (columns left→right).
# Each value is open ports among L=left, R=right, B=bottom.
_STATE_HEADERS: Final[tuple[str, ...]] = (
    "1: AB → AC\n(заводское по умолчанию)",
    "состояние 2:\nABC → AB",
    "состояние 3:\nBC → ABC",
    "состояние 4:\nAC → BC",
)
# Row 0° (CCW end) and row 90° (CW end) open-port sets per column.
# Column headers name the transition (from → to); rows are the extremes.
_ROW_0: Final[tuple[frozenset[str], ...]] = (
    frozenset({"L", "B"}),  # AB
    frozenset({"L", "R", "B"}),  # ABC
    frozenset({"R", "B"}),  # BC
    frozenset({"L", "R"}),  # AC
)
_ROW_90: Final[tuple[frozenset[str], ...]] = (
    frozenset({"L", "R"}),  # AC
    frozenset({"L", "B"}),  # AB
    frozenset({"L", "R", "B"}),  # ABC
    frozenset({"R", "B"}),  # BC
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _stem_t_dirs(open_ports: frozenset[str]) -> tuple[str, str, str]:
    """Three T-bore arms (L/R/B/T); ``T`` = top into the sealed wall.

    The ball always has a T-passage (three openings). When only two body
    ports are open, the third arm faces the blank wall — that port is shut.
    """
    if open_ports == frozenset({"L", "R", "B"}):
        return ("L", "R", "B")
    if open_ports == frozenset({"L", "R"}):
        return ("L", "R", "T")
    if open_ports == frozenset({"L", "B"}):
        return ("L", "B", "T")
    if open_ports == frozenset({"R", "B"}):
        return ("R", "B", "T")
    # Unknown set: still show a full T toward whatever is open + top.
    dirs = [d for d in ("L", "R", "B") if d in open_ports]
    while len(dirs) < 3:
        dirs.append("T")
    return (dirs[0], dirs[1], dirs[2])


def _dir_unit(direction: str) -> tuple[float, float]:
    """Unit vector: L left, R right, B down, T up."""
    mapping = {
        "R": (1.0, 0.0),
        "B": (0.0, 1.0),
        "L": (-1.0, 0.0),
        "T": (0.0, -1.0),
    }
    return mapping[direction]


def _draw_valve(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    cy: int,
    open_ports: frozenset[str],
    scale: float = 1.0,
) -> None:
    """Draw T-body (L / R / B); arrows only on open ports, × on the shut one."""
    s = scale
    body_r = int(28 * s)
    port_len = int(38 * s)
    port_w = int(16 * s)
    # Body circle
    draw.ellipse(
        (cx - body_r, cy - body_r, cx + body_r, cy + body_r),
        outline=_INK,
        width=max(2, int(2 * s)),
    )
    # Ports: left, right, bottom rectangles
    half = port_w // 2
    # left
    draw.rectangle(
        (cx - body_r - port_len, cy - half, cx - body_r, cy + half),
        outline=_INK,
        width=max(2, int(2 * s)),
    )
    # right
    draw.rectangle(
        (cx + body_r, cy - half, cx + body_r + port_len, cy + half),
        outline=_INK,
        width=max(2, int(2 * s)),
    )
    # bottom
    draw.rectangle(
        (cx - half, cy + body_r, cx + half, cy + body_r + port_len),
        outline=_INK,
        width=max(2, int(2 * s)),
    )
    # Flow arrows from center toward open ports
    tip = int(10 * s)
    aw = max(3, int(4 * s))
    if "L" in open_ports:
        x1 = cx - 4
        x2 = cx - body_r - port_len + 6
        draw.line((x1, cy, x2, cy), fill=_INK, width=aw)
        draw.polygon(
            [(x2, cy), (x2 + tip, cy - tip // 2), (x2 + tip, cy + tip // 2)],
            fill=_INK,
        )
    if "R" in open_ports:
        x1 = cx + 4
        x2 = cx + body_r + port_len - 6
        draw.line((x1, cy, x2, cy), fill=_INK, width=aw)
        draw.polygon(
            [(x2, cy), (x2 - tip, cy - tip // 2), (x2 - tip, cy + tip // 2)],
            fill=_INK,
        )
    if "B" in open_ports:
        y1 = cy + 4
        y2 = cy + body_r + port_len - 6
        draw.line((cx, y1, cx, y2), fill=_INK, width=aw)
        draw.polygon(
            [(cx, y2), (cx - tip // 2, y2 - tip), (cx + tip // 2, y2 - tip)],
            fill=_INK,
        )
    # Closed body port: mark × — two open directions ⇒ third shut
    closed = frozenset({"L", "R", "B"}) - open_ports
    x_arm = max(4, int(7 * s))
    for port in closed:
        if port == "L":
            px, py = cx - body_r - port_len // 2, cy
        elif port == "R":
            px, py = cx + body_r + port_len // 2, cy
        else:
            px, py = cx, cy + body_r + port_len // 2
        draw.line((px - x_arm, py - x_arm, px + x_arm, py + x_arm), fill=_INK, width=2)
        draw.line((px - x_arm, py + x_arm, px + x_arm, py - x_arm), fill=_INK, width=2)


def _draw_stem(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    cy: int,
    open_ports: frozenset[str],
    scale: float = 1.0,
) -> None:
    """Top-view stem: always three T-notches; orientation follows the bore."""
    s = scale
    r = int(14 * s)
    draw.rectangle(
        (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2),
        outline=_INK,
        width=1,
    )
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill="#c8c8c8",
        outline=_INK,
        width=1,
    )
    # Always three черточки (T-port). One may face the sealed wall (T).
    notch_w = max(3, int(4 * s))
    inner = int(3 * s)
    for direction in _stem_t_dirs(open_ports):
        ux, uy = _dir_unit(direction)
        x0 = cx + ux * inner
        y0 = cy + uy * inner
        x1 = cx + ux * r
        y1 = cy + uy * r
        draw.line((x0, y0, x1, y1), fill="#ffffff", width=notch_w)
        draw.line((x0, y0, x1, y1), fill=_INK, width=max(1, notch_w - 2))


def _wrap_center(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    lines = text.split("\n")
    x, y = xy
    line_h = int(font.size * 1.25) if hasattr(font, "size") else 18
    total = line_h * len(lines)
    y0 = y - total // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw // 2, y0 + i * line_h), line, font=font, fill=fill)


def compose_flow_scheme() -> Image.Image:
    """Return RGB schematic matching the plant 4×2 flow matrix."""
    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)
    title_f = _font(28)
    head_f = _font(15)
    label_f = _font(16)
    port_f = _font(18)
    foot_f = _font(14)

    title = "Направление потока · 3-ходовой шаровой кран Hoocon 8100"
    bbox = draw.textbbox((0, 0), title, font=title_f)
    draw.text(((_W - (bbox[2] - bbox[0])) // 2, 24), title, font=title_f, fill=_INK)

    # Grid geometry
    left_gutter = 150
    top = 90
    header_h = 70
    row_h = 420
    cols = 4
    usable_w = _W - left_gutter - 40
    col_w = usable_w // cols

    # Outer frame
    draw.rectangle((left_gutter - 8, top, _W - 24, top + header_h + 2 * row_h), outline=_GRID, width=1)
    # Header / row separators
    draw.line((left_gutter - 8, top + header_h, _W - 24, top + header_h), fill=_GRID, width=1)
    draw.line(
        (left_gutter - 8, top + header_h + row_h, _W - 24, top + header_h + row_h),
        fill=_GRID,
        width=1,
    )
    for i in range(1, cols):
        x = left_gutter + i * col_w
        draw.line((x, top, x, top + header_h + 2 * row_h), fill=_GRID, width=1)

    # Corner label
    _wrap_center(draw, "Кран /\nПривод", xy=(left_gutter // 2 + 10, top + header_h // 2), font=label_f, fill=_MUTED)

    for i, header in enumerate(_STATE_HEADERS):
        cx = left_gutter + i * col_w + col_w // 2
        _wrap_center(draw, header, xy=(cx, top + header_h // 2), font=head_f, fill=_INK)

    row_labels = (
        "0°\n(против часовой\nдо упора)",
        "90°\n(по часовой\nдо упора)",
    )
    rows = (_ROW_0, _ROW_90)
    for r, (label, ports_row) in enumerate(zip(row_labels, rows, strict=True)):
        ry = top + header_h + r * row_h
        _wrap_center(
            draw,
            label,
            xy=(left_gutter // 2 + 10, ry + row_h // 2 - 20),
            font=label_f,
            fill=_MUTED,
        )
        for c, ports in enumerate(ports_row):
            cx = left_gutter + c * col_w + col_w // 2
            stem_y = ry + 70
            valve_y = ry + 200
            _draw_stem(draw, cx=cx, cy=stem_y, open_ports=ports, scale=1.15)
            _draw_valve(draw, cx=cx, cy=valve_y, open_ports=ports, scale=1.35)
            # Port letters under valve
            port_y = valve_y + 95
            draw.text((cx - 70, port_y), "A", font=port_f, fill=_INK)
            draw.text((cx + 55, port_y), "C", font=port_f, fill=_INK)
            bbox_b = draw.textbbox((0, 0), "B", font=port_f)
            bw = bbox_b[2] - bbox_b[0]
            draw.text((cx - bw // 2, port_y + 28), "B", font=port_f, fill=_INK)

    foot = (
        "Шток всегда с тремя чёрточками (T-порт): поток в два порта — третий перекрыт. "
        "Ориентируйте корпус A/B/C до установки привода."
    )
    fb = draw.textbbox((0, 0), foot, font=foot_f)
    draw.text(((_W - (fb[2] - fb[0])) // 2, _H - 40), foot, font=foot_f, fill=_MUTED)
    return img


def write_pack(*, pack_dir: Path | None = None) -> Path:
    """Write ``flow-3way.webp`` into the pack directory; return path."""
    root = pack_dir or _PACK_DIR
    root.mkdir(parents=True, exist_ok=True)
    img = compose_flow_scheme()
    buf = BytesIO()
    img.save(buf, format="PNG")
    webp = convert_bytes_to_webp(buf.getvalue())
    out = root / _OUT_NAME
    out.write_bytes(webp)
    return out


def main() -> None:
    """CLI entry: regenerate pack WebP."""
    path = write_pack()
    print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
