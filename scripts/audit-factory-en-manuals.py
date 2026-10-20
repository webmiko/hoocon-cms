#!/usr/bin/env python3
"""Compare factory EN drop (中文 folder) with canonical ``PDF/EN`` on Yandex Disk.

Prints a TSV matrix: pairing, byte identity, text length delta, embedded image
hash deltas. Run from repo root::

    python3 scripts/audit-factory-en-manuals.py
    python3 scripts/audit-factory-en-manuals.py --json /tmp/audit.json

Requires PyMuPDF (``fitz``) — same as manual ETL tooling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import fitz
except ImportError:
    print("PyMuPDF required: pip install pymupdf", file=sys.stderr)
    raise

DEFAULT_FACTORY = Path.home() / "Yandex.Disk.localized/Интскрукции по эксплуатации/英文版说明书"
DEFAULT_EN = Path.home() / "Yandex.Disk.localized/Интскрукции по эксплуатации/PDF/EN"

# Curated factory basename fragments → canonical EN filename (lowercase).
_FACTORY_TO_EN: tuple[tuple[str, str], ...] = (
    ("HVD24_230ST-3F", "hvd-3f-s_st.pdf"),
    ("HVD24_230ST-5F", "hvd-5f-s_st.pdf"),
    ("HVD24_230ST-10F", "hvd-10f-s_st.pdf"),
    ("HVD24_230SX-10F", "hvd-10f-s_sx.pdf"),
    ("SA3FU24_230-DS_DST", "sa3fu-ds_dst.pdf"),
    ("SA5FU24_230-DS_DST", "sa5fu-ds_dst.pdf"),
    ("SA10FU24_230-DS_DST", "sa10fu-ds_dst.pdf"),
    ("SA15FU24_230-DS_DST", "sa15fu-ds_dst.pdf"),
    ("SA3FQU24_230-DS_DST", "sa3fqu-ds_dst.pdf"),
    ("SA10FQU24_230-DS_DST", "sa10fqu-ds_dst.pdf"),
    ("DA10FQU24_230-D_DS", "da10fqu-d_ds.pdf"),
    ("DA5MQU24(230)-A(S)", "da5mqu-a_as.pdf"),
    ("DA5MQU24(230)-D(S)", "da5mqu-d_ds.pdf"),
    ("DA8_16_24_32MU24-A(S)", "da8_16_24_32mu24-a_as.pdf"),
    ("DA8_16_24_32MU24-D(S)", "da8_16_24_32mu24-d_ds.pdf"),
    ("DA8_16_24_32MU230-A(S)", "da8_16_24_32mu230-a_as.pdf"),
    ("DA8_16_24_32MU230-D(S)", "da8_16_24_32mu230-d_ds.pdf"),
    ("HVA5英文版", "hva-5.pdf"),
    ("HVA5Q英文版", "hva-5q.pdf"),
    ("HVD5QX英文版", "hvd-5qx.pdf"),
    ("HVA5QX英文版", "hva-5qx.pdf"),
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).casefold()


def _find_factory(substr: str, root: Path) -> Path | None:
    key = _norm(substr)
    hits = [p for p in root.rglob("*.pdf") if key in _norm(p.name)]
    if len(hits) == 1:
        return hits[0]
    return None


def _image_hashes(path: Path) -> list[tuple[int, str]]:
    doc = fitz.open(path)
    out: list[tuple[int, str]] = []
    for page_i, page in enumerate(doc):
        for img in page.get_images(full=True):
            info = doc.extract_image(img[0])
            digest = hashlib.sha256(info["image"]).hexdigest()[:12]
            out.append((page_i + 1, digest))
    doc.close()
    return out


def _text_len(path: Path) -> int:
    doc = fitz.open(path)
    n = sum(len(page.get_text("text")) for page in doc)
    doc.close()
    return n


@dataclass(slots=True)
class Row:
    factory: str
    en: str
    bytes_equal: bool
    text_len_factory: int
    text_len_en: int
    image_hashes_factory: list[tuple[int, str]]
    image_hashes_en: list[tuple[int, str]]
    note: str = ""


def build_matrix(factory_root: Path, en_root: Path) -> list[Row]:
    rows: list[Row] = []
    mapped_en: set[str] = set()
    for frag, en_name in _FACTORY_TO_EN:
        fp = _find_factory(frag, factory_root)
        ep = en_root / en_name
        if fp is None:
            rows.append(
                Row(
                    factory=f"MISSING:{frag}",
                    en=en_name,
                    bytes_equal=False,
                    text_len_factory=0,
                    text_len_en=_text_len(ep) if ep.is_file() else 0,
                    image_hashes_factory=[],
                    image_hashes_en=_image_hashes(ep) if ep.is_file() else [],
                    note="factory not found",
                ),
            )
            continue
        if not ep.is_file():
            rows.append(
                Row(
                    factory=str(fp.relative_to(factory_root)),
                    en=en_name,
                    bytes_equal=False,
                    text_len_factory=_text_len(fp),
                    text_len_en=0,
                    image_hashes_factory=_image_hashes(fp),
                    image_hashes_en=[],
                    note="EN missing on disk",
                ),
            )
            continue
        mapped_en.add(en_name)
        fb, eb = fp.read_bytes(), ep.read_bytes()
        rows.append(
            Row(
                factory=str(fp.relative_to(factory_root)),
                en=en_name,
                bytes_equal=fb == eb,
                text_len_factory=_text_len(fp),
                text_len_en=_text_len(ep),
                image_hashes_factory=_image_hashes(fp),
                image_hashes_en=_image_hashes(ep),
                note="",
            ),
        )

    for ep in sorted(en_root.glob("*.pdf")):
        if ep.name.casefold() in mapped_en:
            continue
        rows.append(
            Row(
                factory="",
                en=ep.name,
                bytes_equal=False,
                text_len_factory=0,
                text_len_en=_text_len(ep),
                image_hashes_factory=[],
                image_hashes_en=_image_hashes(ep),
                note="EN only (no curated factory map)",
            ),
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", type=Path, default=DEFAULT_FACTORY)
    parser.add_argument("--en", type=Path, default=DEFAULT_EN)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    rows = build_matrix(args.factory, args.en)
    if args.json:
        args.json.write_text(
            json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print("factory\ten\tbytes_eq\ttextΔ\timagesΔ\tnote")
    for r in rows:
        img_eq = r.image_hashes_factory == r.image_hashes_en
        text_delta = r.text_len_factory - r.text_len_en
        print(
            f"{r.factory}\t{r.en}\t{r.bytes_equal}\t{text_delta}\t{img_eq}\t{r.note}",
        )


if __name__ == "__main__":
    main()
