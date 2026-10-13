"""Documentation requests in triage — link to /dokumentaciya for a specific model."""

from __future__ import annotations

import re
from urllib.parse import quote

from supportchat.gigachat.manuals_kb import normalize_product_query

_DOC_INTENT_RE = re.compile(
    r"(?i)\b(?:"
    r"документ|инструкц|паспорт|сертификат|чертеж|схем|pdf|скачать"
    r")\w*\b",
)
_PASSPORT_RE = re.compile(r"(?i)\bпаспорт\w*\b")
_MANUAL_RE = re.compile(r"(?i)\bинструкц\w*\b")
_DOCS_HUB_PATH = "/dokumentaciya"
_DOCS_SKU_RE = re.compile(
    r"(?i)\b((?:da|sa|hv[ad]|8100|h81)[a-z0-9\-]{2,})\b",
)
# «Каталог PDF» / «единый документ» — не паспорт конкретной модели.
_CATALOG_FILE_RE = re.compile(
    r"(?is)(?:"
    r"каталог\w*(?:\s+\w+){0,6}\s+(?:pdf|документ\w*|единый|файл\w*)"
    r"|(?:pdf|единый\s+документ\w*|единый\s+файл\w*).{0,40}?каталог"
    r"|единый\s+каталог"
    r"|каталог\s+продукц"
    r"|единый\s+документ"
    r"|скачать\s+каталог"
    r")",
)
_CATALOG_FILE_REPLY = (
    "Единого PDF-каталога всей продукции нет. "
    "Паспорта и инструкции по моделям собраны на https://hoocon.ru/dokumentaciya — "
    "там можно скачать нужные PDF архивом. "
    "Единый каталог можно запросить у менеджера: укажите, пожалуйста, "
    "электронную почту в этом чате."
)


def extract_docs_sku(text: str) -> str | None:
    """Full article code for documentation hub links (not KB series token)."""
    body = normalize_product_query(text or "")
    matches = _DOCS_SKU_RE.findall(body)
    if not matches:
        return None
    return max(matches, key=len).upper()


def is_document_intent(text: str) -> bool:
    """User asks for manuals, passports, certificates, or PDFs."""
    body = text or ""
    return bool(_DOC_INTENT_RE.search(body) or _CATALOG_FILE_RE.search(body))


def is_catalog_file_request(text: str) -> bool:
    """One combined catalog file, not a manual for a named model."""
    body = text or ""
    if extract_docs_sku(body):
        return False
    return bool(_CATALOG_FILE_RE.search(body))


def build_docs_hub_path(text: str) -> str:
    """Public docs URL, with ``q`` and optional ``kind`` when SKU is known."""
    sku = extract_docs_sku(text)
    if not sku:
        return _DOCS_HUB_PATH
    params = [f"q={quote(sku)}"]
    if _PASSPORT_RE.search(text) and not _MANUAL_RE.search(text):
        params.append("kind=passport")
    elif _MANUAL_RE.search(text) and not _PASSPORT_RE.search(text):
        params.append("kind=manual")
    return f"{_DOCS_HUB_PATH}?{'&'.join(params)}"


def triage_docs_reply(text: str) -> str | None:
    """Suggest documentation hub; for a known SKU — page filtered to that model."""
    body = (text or "").strip()
    if not is_document_intent(body):
        return None
    if is_catalog_file_request(body):
        return _CATALOG_FILE_REPLY
    path = build_docs_hub_path(body)
    sku = extract_docs_sku(body)
    if sku:
        if "kind=passport" in path:
            doc_label = "Паспорт"
        elif "kind=manual" in path:
            doc_label = "Инструкция"
        else:
            doc_label = "Документы"
        return (
            f"{doc_label} по модели {sku} — на странице документации: {path}. "
            "Там можно скачать PDF. Если нужного файла нет — напишите, подключу менеджера."
        )
    return (
        "Инструкции, паспорта и сертификаты — на /dokumentaciya. "
        "Напишите артикул или серию — подскажу ссылку на документы по конкретной модели."
    )
