"""Post-check GigaChat output in triage: whitelist URLs, no guesses."""

from __future__ import annotations

import re

from supportchat.gigachat.triage_docs import is_document_intent
from supportchat.gigachat.triage_product import triage_response_violates_policy

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
_UNCERTAIN_RE = re.compile(
    r"(?i)\b(?:"
    r"не\s+уверен|не\s+знаю|возможно|вероятно|скорее\s+всего|"
    r"по\s+моему\s+мнению|к\s+сожалению,?\s+(?:не\s+)?(?:могу|знаю|найти)|"
    r"интернет|в\s+сети|поискал"
    r")\b",
)
_CATALOG_FOR_DOCS_RE = re.compile(r"(?i)\b(?:раздел\w*\s+)?каталог\w*\b")

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
_UNCERTAIN_HANDOFF_TEXT = "Чтобы ответить точно, подключу менеджера — он ответит здесь. Ожидайте, пожалуйста."
_UNCERTAIN_HANDOFF_NOTE = "Бот не уверен / вопрос вне сценариев первичного приёма."


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


def uncertain_handoff() -> tuple[str, str]:
    """Fallback when triage cannot answer without guessing."""
    return _UNCERTAIN_HANDOFF_TEXT, _UNCERTAIN_HANDOFF_NOTE


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
    for match in _ANY_SITE_PATH_RE.finditer(text or ""):
        if not _path_allowed(match.group(1)):
            return True
    return False


def response_has_foreign_urls(text: str) -> bool:
    """External links are forbidden in triage replies."""
    return bool(_FOREIGN_URL_RE.search(text or ""))


def response_suggests_uncertainty(text: str) -> bool:
    """Model hedges or mentions searching — treat as unsure."""
    return bool(_UNCERTAIN_RE.search(text or ""))


def response_misroutes_docs_to_catalog(text: str, *, user_query: str) -> bool:
    """Passport/manual request but bot sends user to catalog instead of docs."""
    if not is_document_intent(user_query):
        return False
    body = (text or "").lower()
    if "/dokumentaciya" in body or "dokumentaciya" in body:
        return False
    return bool(_CATALOG_FOR_DOCS_RE.search(body))


def triage_output_blocked(text: str, *, user_query: str = "") -> bool:
    """GigaChat reply must not be sent to the client."""
    body = (text or "").strip()
    if not body:
        return True
    if triage_response_violates_policy(body):
        return True
    if response_has_disallowed_site_paths(body):
        return True
    if response_has_foreign_urls(body):
        return True
    if response_suggests_uncertainty(body):
        return True
    if response_misroutes_docs_to_catalog(body, user_query=user_query):
        return True
    return False
