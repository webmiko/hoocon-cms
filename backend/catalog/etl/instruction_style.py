"""Normalize install-guide layout to the DAFU instruction-tab style.

Target shape (see ``series_copy_dafu.SERIES_INSTRUCTIONS``):

- Lead: ``Инструкция…`` (sentence case), not a duplicate ALL-CAPS banner.
- Chapters: ``1. Подготовка к установке`` (h2) — no trailing colon, not ALL CAPS.
- Subheads: ``Проверка совместимости:`` (h3).
- Nested: ``2.1 Установка привода`` with a blank line before the heading.
- Bullets: ``– …`` on one physical line each.
"""

from __future__ import annotations

import re
from typing import Any

from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import Product

_CHAPTER_RE = re.compile(r"^(?P<num>\d+)\.\s+(?P<title>.+?)\s*:?\s*$")
_NESTED_RE = re.compile(r"^(?P<num>\d+\.\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*:?\s*$")
_ALLCAPS_BANNER_RE = re.compile(
    r"^ИНСТРУКЦИЯ\s+ПО\s+УСТАНОВКЕ(?:\s+И\s+УПРАВЛЕНИЮ)?\s*:?\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^[–—\-•·*]\s+")
# Numbered procedure steps (not chapter titles): «1. Вставьте шестигранный ключ…»
_PROCEDURE_STEP_RE = re.compile(
    r"^(?P<num>\d+)\.\s+(?P<title>"
    r"(?:Вставьте|Поворачивайте|Доведите|Поверните|Нажмите|Отпустите|"
    r"Переместите|Ослабьте|Затяните|Подключите|Отключите)\b.+)"
    r"\s*$",
)

# Unnumbered smoke-removal (SA..MU) section titles → chapter numbers.
_BARE_CHAPTER_TITLES: tuple[tuple[str, int], ...] = (
    ("подготовка к установке", 1),
    ("монтаж привода", 2),
    ("электрическое подключение", 3),
    ("управление приводом", 4),
    ("меры безопасности", 5),
    ("техническое обслуживание", 6),
    ("хранение и утилизация", 7),
    ("хранение", 7),
)


def _sentence_case_title(title: str) -> str:
    """First letter upper, rest lower (DAFU chapter style)."""
    t = " ".join(title.split()).strip(" :")
    if not t:
        return t
    if t.isupper() or (len(t) > 3 and t == t.upper()):
        return t[0].upper() + t[1:].lower()
    # Fix nested titles that start lowercase: «пропорциональное…»
    if t[0].islower():
        return t[0].upper() + t[1:]
    return t


def _is_chapter_line(line: str) -> bool:
    if _NESTED_RE.match(line):
        return False
    return bool(_CHAPTER_RE.match(line))


def _is_nested_line(line: str) -> bool:
    return bool(_NESTED_RE.match(line))


def _rewrite_chapter(line: str) -> str:
    m = _CHAPTER_RE.match(line)
    if m is None:
        return line
    return f"{m.group('num')}. {_sentence_case_title(m.group('title'))}"


def _rewrite_nested(line: str) -> str:
    m = _NESTED_RE.match(line)
    if m is None:
        return line
    return f"{m.group('num')} {_sentence_case_title(m.group('title'))}"


def _number_bare_chapter(line: str) -> str | None:
    """Return ``N. Title`` when ``line`` is a known unnumbered chapter title."""
    raw = line.strip().rstrip(":").strip()
    key = raw.casefold()
    for title, num in _BARE_CHAPTER_TITLES:
        if key == title:
            return f"{num}. {_sentence_case_title(raw)}"
    return None


def _fix_common_typos(text: str) -> str:
    out = text
    out = out.replace("наличиинеобходимых", "наличии необходимых")
    out = re.sub(r"\b0\.5\s*мм", "0,5 мм", out)
    out = re.sub(r"\b0\.5\s*mm", "0,5 мм", out, flags=re.IGNORECASE)
    return out


def normalize_instruction_style(text: str) -> str:
    """Rewrite an install guide toward the DAFU instruction-tab layout.

    Args:
        text: Raw ``Product.instructions`` / category instructions.

    Returns:
        Normalized text (glossary + layout). Empty input unchanged.
    """
    if not text or not text.strip():
        return text

    raw = _fix_common_typos(text.replace("\r\n", "\n").replace("\r", "\n"))
    lines_in = raw.split("\n")
    lines_out: list[str] = []

    i = 0
    while i < len(lines_in):
        line = lines_in[i].rstrip()
        stripped = line.strip()

        # Drop ALL-CAPS banner when a normal «Инструкция…» lead follows.
        if _ALLCAPS_BANNER_RE.match(stripped):
            j = i + 1
            while j < len(lines_in) and not lines_in[j].strip():
                j += 1
            if j < len(lines_in) and lines_in[j].strip().lower().startswith("инструкция"):
                i += 1
                continue
            # Banner alone → soften to sentence-case lead without colon.
            lines_out.append("Инструкция по установке и управлению")
            i += 1
            continue

        if not stripped:
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            i += 1
            continue

        numbered_bare = _number_bare_chapter(stripped)
        if numbered_bare is not None and not _BULLET_RE.match(stripped):
            stripped = numbered_bare

        proc = _PROCEDURE_STEP_RE.match(stripped)
        if proc is not None:
            lines_out.append(f"– {proc.group('title').strip()}")
            i += 1
            continue

        if _is_nested_line(stripped):
            rewritten = _rewrite_nested(stripped)
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            lines_out.append(rewritten)
            i += 1
            continue

        if _is_chapter_line(stripped):
            rewritten = _rewrite_chapter(stripped)
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            lines_out.append(rewritten)
            i += 1
            continue

        lines_out.append(stripped)
        i += 1

    # Collapse runs of blank lines; trim edges.
    compact: list[str] = []
    for line in lines_out:
        if line == "" and (not compact or compact[-1] == ""):
            continue
        compact.append(line)
    while compact and compact[0] == "":
        compact.pop(0)
    while compact and compact[-1] == "":
        compact.pop()

    # No blank lines between adjacent bullets (one list block in the UI).
    tight: list[str] = []
    for i, line in enumerate(compact):
        if (
            line == ""
            and tight
            and _BULLET_RE.match(tight[-1])
            and i + 1 < len(compact)
            and _BULLET_RE.match(compact[i + 1])
        ):
            continue
        tight.append(line)

    joined = "\n".join(tight)
    return normalize_tech_copy(joined)


def apply_instruction_style(*, dry_run: bool = False) -> dict[str, Any]:
    """Normalize ``Product.instructions`` for every product that has a guide.

    Args:
        dry_run: When True, count only.

    Returns:
        Counters: checked, updated, unchanged, dry_run.
    """
    updated = 0
    unchanged = 0
    checked = 0
    samples: list[str] = []

    for product in (
        Product.objects.exclude(instructions="")
        .exclude(
            instructions__isnull=True,
        )
        .order_by("slug")
    ):
        checked += 1
        original = product.instructions or ""
        # DAFU canon is owned by enrich_dafu — still run style pass for safety.
        rewritten = normalize_instruction_style(original)
        if rewritten == original:
            unchanged += 1
            continue
        updated += 1
        if len(samples) < 8:
            samples.append(product.slug)
        if not dry_run:
            product.instructions = rewritten
            product.save(update_fields=["instructions"])

    return {
        "checked": checked,
        "updated": updated,
        "unchanged": unchanged,
        "dry_run": dry_run,
        "samples": samples,
    }
