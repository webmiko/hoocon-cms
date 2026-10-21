"""Shared work marks for company cards and leads.

The catalog is the filter set managers asked for in the 21.10.2026
outreach workbook: queue state, stop flags, and the niche/relevance
marks from the separate «base» sheet. Codes are stable; titles are Russian.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

# Queue and flags parsed from the «Заметки» column of the client template.
_QUEUE: tuple[tuple[str, str], ...] = (
    ("not_called", "Не прозвонен"),
    ("new_lead", "Новый лид"),
    ("no_answer", "Не дозвонились"),
    ("in_work", "В работе"),
    ("interested", "Заинтересованы"),
    ("quote_sent", "КП выслано"),
    ("confirmed", "Подтверждён"),
)
_FLAGS: tuple[tuple[str, str], ...] = (
    ("objection", "Есть возражение"),
    ("do_not_call", "Не звонить"),
    ("existing_client", "Уже работаем"),
    ("profile_mismatch", "Профиль не совпадает"),
    ("winding_down", "Сворачивает производство"),
    ("duplicate", "Дубль базы"),
    ("verify_base", "Сверить с базой"),
    ("need_data", "Нужны данные"),
    ("inn_mismatch", "Расхождение названия и ИНН"),
    ("prepaid_only", "Только предоплата"),
    ("low_priority", "Хвост очереди"),
    ("reference", "Эталон"),
    ("checko_warning", "Предупреждение Checko"),
)
_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("relevance-high", "Релевантность: высокая"),
    ("relevance-medium", "Релевантность: средняя"),
    ("relevance-low", "Релевантность: низкая"),
    ("niche-armature", "Ниша: трубопроводная арматура"),
    ("niche-hvac", "Ниша: дистрибьюторы HVAC"),
    ("niche-fire", "Ниша: противопожарные подрядчики"),
    ("niche-industry", "Ниша: промышленные предприятия"),
    ("niche-industrial", "Ниша: промышленные дистрибьюторы"),
    ("region-pfo", "Регион: ПФО"),
    ("region-ufo", "Регион: ЮФО"),
    ("region-skfo", "Регион: СКФО"),
    ("region-cfo", "Регион: ЦФО"),
    ("region-szfo", "Регион: СЗФО"),
    ("region-urfo", "Регион: УрФО"),
    ("region-sfo", "Регион: СФО"),
    ("region-dfo", "Регион: ДФО"),
)

KIND_QUEUE = "queue"
KIND_FLAG = "flag"
KIND_SEGMENT = "segment"


@dataclass(frozen=True)
class LabelSpec:
    """One global mark. ``code`` is the filter key, ``name`` is the admin title."""

    code: str
    name: str
    kind: str
    sort: int


def _specs(rows: tuple[tuple[str, str], ...], kind: str, start: int) -> tuple[LabelSpec, ...]:
    return tuple(
        LabelSpec(code=code, name=name, kind=kind, sort=start + offset) for offset, (code, name) in enumerate(rows)
    )


WORK_LABELS: tuple[LabelSpec, ...] = (
    _specs(_QUEUE, KIND_QUEUE, 10) + _specs(_FLAGS, KIND_FLAG, 40) + _specs(_SEGMENTS, KIND_SEGMENT, 80)
)
WORK_LABEL_BY_CODE: dict[str, LabelSpec] = {item.code: item for item in WORK_LABELS}

_PLAN_RE = re.compile(r"Звонок по плану:\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", re.IGNORECASE)
_LEGAL_PREFIX = re.compile(r"^(?:ооо|оао|зао|пао|ао|ип|нпп|нпк|нпф|нтц|тд|ск|пп)\s+")
_CONTACT_RE = re.compile(
    r"(?:технический директор|генеральный директор|ген\.?\s*директор|контакт|директор)"
    r"\s*[:\-]?\s*"
    r"([А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z.\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z.\-]*){0,4})",
    re.IGNORECASE,
)
_NICHE_CODES = {
    "трубопроводная арматура": "niche-armature",
    "дистрибьюторы hvac": "niche-hvac",
    "противопожарные подрядчики": "niche-fire",
    "промышленные предприятия": "niche-industry",
    "дистрибьюторы (промышленные)": "niche-industrial",
}
_REGION_CODES = {
    "пфо": "region-pfo",
    "юфо": "region-ufo",
    "скфо": "region-skfo",
    "цфо": "region-cfo",
    "сзфо": "region-szfo",
    "урфо": "region-urfo",
    "сфо": "region-sfo",
    "дфо": "region-dfo",
}
_RELEVANCE_CODES = {
    "высок": "relevance-high",
    "средн": "relevance-medium",
    "низк": "relevance-low",
}
_RELEVANCE_VALUE = {
    "relevance-high": "high",
    "relevance-medium": "medium",
    "relevance-low": "low",
}


def loose_company_key(raw: str) -> str:
    """Company match key without legal-form prefixes and quotes.

    «ООО «АЗ АТОМ»» and «АЗ АТОМ» share a key. The ordinary company_key
    keeps the full label so routing rules stay exact.
    """
    from leads.services import normalize_company_label

    text = normalize_company_label(raw)
    previous = None
    while text and text != previous:
        previous = text
        text = _LEGAL_PREFIX.sub("", text).strip()
    return text


def labels_for_note(note: str) -> frozenset[str]:
    """Marks implied by a template «Заметки» cell.

    The first segment is the queue state. The rest of the cell adds flags
    (do-not-call, prepay, Checko warning). Expectations are the phrases
    in the 21.10 workbook, not a dump of this function.
    """
    text = (note or "").casefold().replace("ё", "е")
    if not text.strip():
        return frozenset()
    first = text.split("|", 1)[0].strip()
    labels: set[str] = set()
    if first.startswith("не прозвонен"):
        labels.add("not_called")
    if first.startswith("новый лид"):
        labels.add("new_lead")
    if first.startswith("не дозвонились") or first.startswith("ндз"):
        labels.add("no_answer")
    if first.startswith("в работе") or "повторный контакт в работе" in first:
        labels.add("in_work")
    if first.startswith("заинтересованы"):
        labels.add("interested")
    if first.startswith("кп выслано"):
        labels.add("quote_sent")
    if first.startswith("подтвержден"):
        labels.add("confirmed")
    if "возражен" in text:
        labels.add("objection")
    if "профиль не совпадает" in text:
        labels.add("profile_mismatch")
    if "сворачивает производство" in text:
        labels.add("winding_down")
    if "не звонить" in text or "не звоним" in text or "исключ" in text or "приводы не покупают" in text:
        labels.add("do_not_call")
    if "им ничего не нужно" in text:
        labels.add("do_not_call")
    if "уже работаем" in text:
        labels.add("existing_client")
        labels.add("do_not_call")
    if "действующий клиент" in text:
        labels.add("existing_client")
    if "дубль" in text:
        labels.add("duplicate")
    if "сверить с базой" in text or "сверить с действующ" in text:
        labels.add("verify_base")
    if "найти инн" in text or "найти операционное" in text or "требуется найти" in text or "расхождение" in text:
        labels.add("need_data")
    if "расхождение" in text:
        labels.add("inn_mismatch")
    if "только по предоплате" in text or "только предоплата" in text or "отгрузка по предоплате" in text:
        labels.add("prepaid_only")
    if any(
        phrase in text
        for phrase in (
            "хвост очереди",
            "не в первой очереди",
            "низкий приоритет",
            "последняя очередь",
            "низкий потенциал",
            "слабый лид",
        )
    ):
        labels.add("low_priority")
    if "эталон" in text:
        labels.add("reference")
    if "⚠" in note or "checko" in text:
        labels.add("checko_warning")
    return frozenset(labels)


def planned_call_date(note: str, *, today: date) -> date | None:
    """Date from «Звонок по плану: 26.10». Year defaults to ``today``.

    A date more than 45 days behind ``today`` rolls to the next year so a
    January import of an October plan does not land in the past year.
    """
    match = _PLAN_RE.search(note or "")
    if match is None:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    try:
        found = date(year, month, day)
    except ValueError:
        return None
    if match.group(3) is None and found < today - timedelta(days=45):
        try:
            found = date(year + 1, month, day)
        except ValueError:
            return None
    return found


def extract_contact_name(profile: str) -> str:
    """Person named after «контакт» or «директор» in a profile sentence."""
    match = _CONTACT_RE.search(profile or "")
    if match is None:
        return ""
    return " ".join(match.group(1).split())


def niche_title(raw: str) -> str:
    """Human niche: drop the leading catalog number («3 — …»)."""
    text = " ".join((raw or "").replace("—", "-").split())
    if "-" in text:
        _prefix, _, tail = text.partition("-")
        if _prefix.strip().split(" ")[0].isdigit() or _prefix.strip().isdigit():
            return tail.strip()
    return text.strip()


def niche_label_code(title: str) -> str:
    """Stable segment code for a niche title. Unknown titles get a slug."""
    key = " ".join(title.casefold().replace("ё", "е").split())
    known = _NICHE_CODES.get(key)
    if known:
        return known
    slug = re.sub(r"[^a-z0-9а-я]+", "-", key).strip("-")[:40]
    return f"niche-{slug}" if slug else ""


def relevance_label_code(raw: str) -> str:
    """``relevance-high`` and siblings from «Высокая — …»."""
    head = (raw or "").casefold().replace("ё", "е").split("—", 1)[0].split("-", 1)[0].strip()
    for prefix, code in _RELEVANCE_CODES.items():
        if head.startswith(prefix):
            return code
    return ""


def relevance_value(code: str) -> str:
    """Company.relevance choice for a relevance label code."""
    return _RELEVANCE_VALUE.get(code, "")


def region_label_code(raw: str) -> str:
    """``region-pfo`` for «ПФО». Unknown districts stay a company field only."""
    key = " ".join((raw or "").casefold().replace("ё", "е").split())
    return _REGION_CODES.get(key, "")
