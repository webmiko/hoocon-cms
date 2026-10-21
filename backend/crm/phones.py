"""Several phone numbers on one company card.

A single text cell glues every digit together, and the softphone refuses a
number longer than 15 digits. Each number is stored and dialed on its own.
"""

from __future__ import annotations

import re
from typing import Any

from crm.telephony import normalize_phone_digits

_NOTE_PARENS = re.compile(r"\([^)]*[а-яёА-ЯЁ][^)]*\)")
_SPLIT = re.compile(r"[;\n,]+")


def split_phone_numbers(raw: str) -> list[str]:
    """Display numbers from one cell.

    ``+7 (843) 554-00-45; +7 (843) 555-53-96`` is two numbers. A Russian
    note in parentheses, such as «(актуально по сайту)», is not a number.
    """
    text = _NOTE_PARENS.sub(" ", raw or "")
    found: list[str] = []
    seen: set[str] = set()
    for chunk in _SPLIT.split(text):
        number = " ".join(chunk.split()).strip(" .")
        digits = normalize_phone_digits(number)
        if len(digits) < 5 or digits in seen:
            continue
        seen.add(digits)
        found.append(number)
    return found


def join_phone_numbers(*parts: str) -> str:
    """One stored string, semicolon-separated, without duplicates."""
    found: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for number in split_phone_numbers(part):
            digits = normalize_phone_digits(number)
            if digits in seen:
                continue
            seen.add(digits)
            found.append(number)
    return "; ".join(found)[:300]


def sync_company_phones(company: object) -> None:
    """Index every number on the company so a call can find the card."""
    from crm.models import CompanyPhone

    phone = getattr(company, "phone", "") or ""
    company_id = getattr(company, "pk", None)
    if not company_id:
        return
    numbers = split_phone_numbers(phone)
    existing = {row.phone_digits: row for row in CompanyPhone.objects.filter(company_id=company_id)}
    keep: set[str] = set()
    for index, number in enumerate(numbers):
        digits = normalize_phone_digits(number)[:20]
        keep.add(digits)
        row = existing.get(digits)
        if row is None:
            CompanyPhone.objects.create(
                company_id=company_id,
                number=number[:50],
                phone_digits=digits,
                sort=index,
            )
            continue
        if row.number != number[:50] or row.sort != index:
            row.number = number[:50]
            row.sort = index
            row.save(update_fields=["number", "sort"])
    stale = [row.pk for digits, row in existing.items() if digits not in keep]
    if stale:
        CompanyPhone.objects.filter(pk__in=stale).delete()


def company_for_phone(phone: str) -> Any:
    """Company whose card lists this number, or None."""
    from crm.models import CompanyPhone

    digits = normalize_phone_digits(phone)
    if len(digits) < 5:
        return None
    row = CompanyPhone.objects.select_related("company").filter(phone_digits=digits).order_by("pk").first()
    if row is None:
        return None
    return row.company
