"""Title / description length helpers for Google + Yandex snippets.

Spec: docs/seo-meta-yandex-google.md — target title ≤60 with brand,
description ≤160.
"""

from __future__ import annotations

from config.seo.routes import SITE_NAME
from config.seo.sanitize import plain_text_for_meta

# Full <title> including brand suffix (snippet-safe for Google/Yandex).
TITLE_MAX_LEN = 60
# Leave room for `` — {SITE_NAME}`` when brand is appended.
_BRAND_SUFFIX = f" — {SITE_NAME}"
TITLE_PARTIAL_MAX = TITLE_MAX_LEN - len(_BRAND_SUFFIX)
DESCRIPTION_MAX_LEN = 160


def format_branded_title(partial: str | None) -> str:
    """Build page title with brand; keep full string within TITLE_MAX_LEN.

    Args:
        partial: Page-specific title without brand, or None for default.

    Returns:
        Title string safe for SERP display length.
    """
    if not partial:
        from config.seo.routes import DEFAULT_TITLE

        return plain_text_for_meta(DEFAULT_TITLE, max_len=TITLE_MAX_LEN)
    text = plain_text_for_meta(partial, max_len=TITLE_PARTIAL_MAX)
    if SITE_NAME in text:
        return plain_text_for_meta(text, max_len=TITLE_MAX_LEN)
    return plain_text_for_meta(f"{text}{_BRAND_SUFFIX}", max_len=TITLE_MAX_LEN)


def format_meta_description(value: str, *, max_len: int = DESCRIPTION_MAX_LEN) -> str:
    """Plain description capped for meta snippets."""
    return plain_text_for_meta(value, max_len=max_len)


def sku_kind_for_title(category_name: str | None) -> str:
    """One searchable noun for a SERP title: кран, комплект, адаптер or привод."""
    name = (category_name or "").casefold()
    if "кран" in name:
        return "кран"
    if "адаптер" in name:
        return "адаптер"
    if "комплект" in name:
        return "комплект"
    if "кронштейн" in name:
        return "кронштейн"
    return "привод"


def sku_meta_title_partial(
    sku_code: str,
    *,
    moment: str = "",
    voltage: str = "",
    analog: str = "",
    kind: str = "",
) -> str:
    """PDP title body: код, тип, момент, напряжение и аналог Belimo, если влезает.

    Google переписывал короткий ``код — 230 В``. Момент и аналог отличают
    соседние исполнения в сниппете. Хвост отбрасывается, если не входит в
    ``TITLE_PARTIAL_MAX``.

    Args:
        sku_code: Public article code.
        moment: Torque highlight (e.g. ``5 Нм``).
        voltage: Voltage highlight, shortened to ``24 В`` / ``230 В``.
        analog: Belimo code, without the word Belimo.
        kind: Short noun from :func:`sku_kind_for_title`.

    Returns:
        Partial title without brand suffix.
    """
    code = (sku_code or "").strip() or "SKU"
    volt = _short_voltage_for_title(voltage)
    moment_bit = " ".join((moment or "").split())
    if len(moment_bit) > 12:
        moment_bit = ""
    analog_bit = " ".join((analog or "").split())
    kind_bit = (kind or "").strip()
    parts = [code]
    if kind_bit:
        parts.append(kind_bit)
    if moment_bit:
        parts.append(moment_bit)
    if volt:
        parts.append(volt)
    partial = " ".join(parts)
    if analog_bit:
        with_analog = f"{partial}, аналог {analog_bit}"
        if len(with_analog) <= TITLE_PARTIAL_MAX:
            partial = with_analog
    if len(partial) <= TITLE_PARTIAL_MAX:
        return partial
    shorter = [code]
    if moment_bit:
        shorter.append(moment_bit)
    if volt:
        shorter.append(volt)
    partial = " ".join(shorter)
    if len(partial) <= TITLE_PARTIAL_MAX:
        return partial
    return partial[:TITLE_PARTIAL_MAX]


def _short_voltage_for_title(voltage: str) -> str:
    """Collapse long Belimo voltage canon to ``24 В`` / ``230 В`` for SERP."""
    text = " ".join((voltage or "").split())
    if not text:
        return ""
    from catalog.etl.tech_copy import detect_voltage_family

    family = detect_voltage_family(text)
    if family == "24":
        return "24 В"
    if family == "230":
        return "230 В"
    # Already short or unknown — keep a compact form.
    if len(text) <= 12:
        return text
    return text[:12].rsplit(" ", 1)[0] if " " in text[:12] else text[:12]


def sku_meta_description(
    sku_code: str,
    *,
    category_name: str | None = None,
    moment: str = "",
    voltage: str = "",
    analog: str = "",
) -> str:
    """Snippet that differs by torque, voltage and Belimo code, not only the article.

    Args:
        sku_code: Public article code.
        category_name: Category label.
        moment: Torque highlight.
        voltage: Voltage highlight.
        analog: Belimo code.

    Returns:
        Description within ``DESCRIPTION_MAX_LEN``.
    """
    code = (sku_code or "").strip() or "SKU"
    bits = [f"{code}:"]
    if category_name and category_name.strip():
        bits.append(f"{plain_text_for_meta(category_name, max_len=60)}.")
    else:
        bits.append("электропривод вентиляции Hoocon.")
    facts: list[str] = []
    moment_bit = " ".join((moment or "").split())
    if moment_bit:
        facts.append(moment_bit)
    volt = _short_voltage_for_title(voltage)
    if volt:
        facts.append(volt)
    if facts:
        bits.append(f"{' '.join(facts)}.")
    analog_bit = " ".join((analog or "").split())
    if analog_bit:
        bits.append(f"Аналог Belimo {analog_bit}.")
    bits.append("Паспорт PDF, запрос КП у Hoocon.")
    return format_meta_description(" ".join(bits))
