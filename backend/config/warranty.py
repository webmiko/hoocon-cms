"""Canonical product warranty for Hoocon (RF deliveries).

Change ``WARRANTY_MONTHS`` once — sentences and short labels follow.
HTML fixtures under ``content/fixtures/`` must stay in sync manually
(``24&nbsp;мес.`` / ``24&nbsp;месяца``).
"""

from __future__ import annotations

WARRANTY_MONTHS = 24


def warranty_months_word(months: int = WARRANTY_MONTHS) -> str:
    """Return Russian noun form for *месяц* after a number.

    Args:
        months: Warranty length in months.

    Returns:
        One of ``месяц`` / ``месяца`` / ``месяцев``.
    """
    n = abs(int(months)) % 100
    n1 = n % 10
    if 11 <= n <= 14:
        return "месяцев"
    if n1 == 1:
        return "месяц"
    if 2 <= n1 <= 4:
        return "месяца"
    return "месяцев"


def warranty_duration(months: int = WARRANTY_MONTHS) -> str:
    """Human duration, e.g. ``24 месяца``."""
    return f"{int(months)} {warranty_months_word(months)}"


def warranty_duration_nbsp(months: int = WARRANTY_MONTHS) -> str:
    """HTML duration with non-breaking space, e.g. ``24&nbsp;месяца``."""
    return f"{int(months)}&nbsp;{warranty_months_word(months)}"


def warranty_short(months: int = WARRANTY_MONTHS) -> str:
    """Compact label for dashboards, e.g. ``24 мес.``."""
    return f"{int(months)} мес."


def warranty_short_nbsp(months: int = WARRANTY_MONTHS) -> str:
    """Compact HTML label, e.g. ``24&nbsp;мес.``."""
    return f"{int(months)}&nbsp;мес."


# Ready-made phrases for SKU/product copy and CMS seed.
WARRANTY_DURATION = warranty_duration()
WARRANTY_LINE = f"Гарантия: {WARRANTY_DURATION}."
WARRANTY_BULLET = f"– Гарантия: {WARRANTY_DURATION}."
WARRANTY_COMPANY_LI = f"Гарантия {WARRANTY_DURATION} на приводы линейки."
