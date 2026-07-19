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


def sku_meta_title_partial(
    sku_code: str,
    *,
    moment: str = "",
    voltage: str = "",
) -> str:
    """Short PDP title body (before brand): артикул + ключевые ТТХ.

    Args:
        sku_code: Public article code.
        moment: Optional torque highlight (e.g. ``8 Нм``).
        voltage: Optional voltage highlight (e.g. ``230 В``).

    Returns:
        Partial title without brand suffix.
    """
    code = (sku_code or "").strip() or "SKU"
    specs = ", ".join(part for part in (moment.strip(), voltage.strip()) if part)
    if specs:
        return f"{code} — {specs}"
    return f"{code} — электропривод ОВК"


def sku_meta_description(
    sku_code: str,
    *,
    category_name: str | None = None,
) -> str:
    """Compact unique description for product SERP snippet."""
    code = (sku_code or "").strip() or "SKU"
    if category_name and category_name.strip():
        cat = plain_text_for_meta(category_name, max_len=60)
        body = f"{code}: {cat}. Паспорт PDF, подбор аналогов Belimo, запрос КП у Hoocon."
    else:
        body = f"{code}: электропривод ОВК Hoocon. Паспорт PDF, фильтры по ТТХ, запрос коммерческого предложения."
    return format_meta_description(body)
