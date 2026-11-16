"""Which letters from a mailbox belong in the CRM.

The folder is not the filter: «Заявки» also receives ordinary mail.
A new letter is taken when its subject explicitly asks for a consultation
or a quote. A reply is taken when it continues a thread already stored.
"""

from __future__ import annotations

import re

from django.db import models


class MailIntake(models.TextChoices):
    """How much of a mailbox folder is imported."""

    REQUESTS = "requests", "Только заявки и запросы КП"
    THREADS = "threads", "Только продолжение переписки в CRM"
    ALL = "all", "Вся папка"


# One fragment per line. «кп» is a whole word: «покупка» must not qualify.
DEFAULT_INTAKE_SUBJECTS = "заявка\nконсультац\nзапрос\nкоммерческ\nкп"

_YO = str.maketrans({"ё": "е", "Ё": "Е"})
_SHORT_NEEDLE = 2


def intake_needles(raw: str) -> tuple[str, ...]:
    """Subject fragments for this mailbox. Empty text uses the standard list."""
    lines = [_fold(line) for line in (raw or "").splitlines()]
    lines = [line for line in lines if line]
    if lines:
        return tuple(lines)
    return tuple(_fold(line) for line in DEFAULT_INTAKE_SUBJECTS.splitlines())


def subject_is_request(subject: str, raw_needles: str) -> bool:
    """True when the subject explicitly asks for a consultation or a quote."""
    text = _fold(subject)
    if not text:
        return False
    for needle in intake_needles(raw_needles):
        if len(needle) <= _SHORT_NEEDLE:
            if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text):
                return True
            continue
        if needle in text:
            return True
    return False


def _fold(value: str) -> str:
    """Case-fold and treat ё as е, so the list does not depend on spelling."""
    return (value or "").translate(_YO).casefold().strip()
