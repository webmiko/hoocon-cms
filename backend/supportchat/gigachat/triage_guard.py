"""Triage static replies and the full-mode output guard (URL whitelist, KB SKUs)."""

from __future__ import annotations

import re

# Public routes the bot may mention (prefix match).
ALLOWED_SITE_PATH_PREFIXES: tuple[str, ...] = (
    "/dokumentaciya",
    "/catalog",
    "/gde-kupit",
    "/kontakty",
    "/consultation",
    "/faq",
    "/zavod",
    "/company",
    "/rfq",
    "/search",
    "/#podbor",
    "/",
)

_ANY_SITE_PATH_RE = re.compile(
    r"(?<![\w.])"
    r"(/(?:[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*)"
    r"(?:\?[^\s.,;:!?)»\"']+)?(?:\#[a-z0-9-]+)?|/\#[a-z0-9-]+)",
    re.IGNORECASE,
)
_FOREIGN_URL_RE = re.compile(r"https?://(?!(?:www\.)?hoocon\.ru)[^\s]+", re.IGNORECASE)
# Внутренние пути репозитория — не публичные URL сайта.
_INTERNAL_PATH_RE = re.compile(
    r"(?i)/(?:_manuals-ru|_инструкции-pdf|_pack|_docs|_универсальная)\b",
)
_GREETING_RE = re.compile(
    r"(?i)^(?:"
    r"привет(?:ствую)?|здравствуйте|добрый\s+(?:день|вечер|утро)|"
    r"доброе\s+утро|hello|hi|hey|салют"
    r")[!.,?\s]*$",
)
_VAGUE_HELP_RE = re.compile(
    r"(?i)^(?:"
    r"чем\s+(?:вы\s+)?можете\s+помочь|чем\s+помочь|помогите|"
    r"что\s+вы\s+умеете|что\s+можете|help"
    r")[!.,?\s]*$",
)

_GREETING_REPLY = (
    "Чем могу помочь? Могу подсказать раздел сайта, ссылку на документацию по артикулу "
    "или подключить менеджера для подбора привода."
)
_UNCERTAIN_BRANCH_TEXT = (
    "По этому вопросу точнее ответит менеджер. Напишите «позовите менеджера», "
    "когда будете готовы, или переформулируйте запрос — подскажу раздел сайта или документацию."
)


def triage_greeting_reply(text: str) -> str | None:
    """Static welcome — no GigaChat API (reliable on «Привет» / «Добрый день»)."""
    if is_greeting_intent(text):
        return _GREETING_REPLY
    return None


def is_greeting_intent(text: str) -> bool:
    """Short greeting or «чем помочь» — единственный случай для GigaChat в triage."""
    body = (text or "").strip()
    if not body:
        return False
    if len(body) > 120:
        return False
    return bool(_GREETING_RE.match(body) or _VAGUE_HELP_RE.match(body))


def uncertain_branch_reply() -> str:
    """Fallback when triage cannot answer without guessing."""
    return _UNCERTAIN_BRANCH_TEXT


def _path_allowed(path: str) -> bool:
    normalized = (path or "").strip()
    if not normalized.startswith("/"):
        return False
    for prefix in ALLOWED_SITE_PATH_PREFIXES:
        if (
            normalized == prefix
            or normalized.startswith(f"{prefix}?")
            or normalized.startswith(
                f"{prefix}/",
            )
        ):
            return True
        if prefix == "/" and normalized == "/":
            return True
    if normalized.startswith("/#"):
        return True
    return False


def response_has_disallowed_site_paths(text: str) -> bool:
    """Bot mentioned a site path outside the public whitelist."""
    if _INTERNAL_PATH_RE.search(text or ""):
        return True
    for match in _ANY_SITE_PATH_RE.finditer(text or ""):
        if not _path_allowed(match.group(1)):
            return True
    return False


def response_has_foreign_urls(text: str) -> bool:
    """External links are forbidden in triage replies."""
    return bool(_FOREIGN_URL_RE.search(text or ""))


# ── Full-mode output guard ──

_SPRING_RETURN_RE = re.compile(
    r"(?i)\b(?:пружин\w*|fail[-\s]?safe|фейл[-\s]?сейф|аварийн\w*\s+возврат)",
)
_SKU_RE = re.compile(
    r"\b(?:da|sa|hv[ad]?)-?\d+(?:mu|fu|mqu)(?:24|230)?(?:-[a-z0-9/]+)?",
    re.IGNORECASE,
)
_MU_SKU_RE = re.compile(r"\b(?:da|sa|hv[ad]?)-?\d+mu", re.IGNORECASE)
_FU_SKU_RE = re.compile(r"\b(?:da|sa|hv[ad]?)-?\d+fu", re.IGNORECASE)
_SKU_SUFFIX_24_RE = re.compile(r"\b(?:da|sa|hv[ad]?)-?\d+(?:mu|fu)24\b", re.IGNORECASE)
_SKU_SUFFIX_230_RE = re.compile(r"\b(?:da|sa|hv[ad]?)-?\d+(?:mu|fu)230\b", re.IGNORECASE)
_WANTS_24_RE = re.compile(r"(?i)\b(?:на\s+)?24\s*(?:в\b|v\b|volt|вольт)")
_WANTS_230_RE = re.compile(r"(?i)\b(?:на\s+)?(?:230|220)\s*(?:в\b|v\b|volt|вольт)")


def reply_violates_requested_specs(text: str, *, user_texts: list[str]) -> bool:
    """Model SKU contradicts a requirement the client stated in the thread."""
    body = (text or "").strip()
    joined = " ".join(user_texts)
    if _SPRING_RETURN_RE.search(joined):
        # Просят пружинный возврат → MU (без пружины) без FU-варианта = нарушение.
        if _MU_SKU_RE.search(body) and not _FU_SKU_RE.search(body):
            return True
    if _WANTS_24_RE.search(joined):
        if _SKU_SUFFIX_230_RE.search(body) and not _SKU_SUFFIX_24_RE.search(body):
            return True
    if _WANTS_230_RE.search(joined):
        if _SKU_SUFFIX_24_RE.search(body) and not _SKU_SUFFIX_230_RE.search(body):
            return True
    return False


def reply_mentions_unknown_sku(text: str) -> bool:
    """Reply names a SKU that does not exist in the packaged KB."""
    from supportchat.gigachat.kb_text import load_kb_text

    body = (text or "").strip()
    if not body:
        return False
    try:
        kb = load_kb_text().upper()
    except Exception:  # noqa: BLE001 — без базы не блокируем ответ
        return False
    for match in _SKU_RE.finditer(body):
        sku = match.group(0).upper()
        # Вариант суффикса (-D/DS, -S/ST…) отсекаем с конца, не от серии:
        # «HVD-6MU230-S/ST» → «HVD-6MU230», «DA6MU230-D/DS» → «DA6MU230».
        base = re.sub(r"-[A-Z0-9/]+$", "", sku)
        candidates = {sku, base, sku.replace("-", ""), base.replace("-", "")}
        if not any(candidate in kb for candidate in candidates):
            return True
    return False


def full_output_blocked(text: str, *, user_texts: list[str]) -> bool:
    """Full-mode reply must not reach the client (KB grounding violated)."""
    body = (text or "").strip()
    if not body:
        return True
    if response_has_disallowed_site_paths(body):
        return True
    if response_has_foreign_urls(body):
        return True
    if reply_violates_requested_specs(body, user_texts=user_texts):
        return True
    if reply_mentions_unknown_sku(body):
        return True
    return False
