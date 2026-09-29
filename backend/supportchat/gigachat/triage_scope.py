"""Out-of-scope topics: static refusal without GigaChat."""

from __future__ import annotations

import re

# Не ОВК / не Hoocon — вежливый отказ без эскалации.
_OUT_OF_SCOPE_RE = re.compile(
    r"(?i)\b(?:"
    r"ворот\w*|роллет\w*|шлагбаум\w*|"
    r"двер[ьи]\s+(?:гараж|входн|межкомнат)|"
    r"рецепт|кулинар|погод|политик|"
    r"крипт|bitcoin|ставк[аи]\s+на\s+спорт"
    r")\b",
)

_OUT_OF_SCOPE_REPLY = (
    "Hoocon — электроприводы для вентиляции и кондиционирования (заслонки, клапаны, шаровые краны). "
    "По воротам, дверям и другим темам вне ОВК я не консультирую. "
    "Если нужен привод для вентиляции — опишите задачу или напишите «менеджер»."
)

# Болтовня не по теме (анекдоты, шутки, «скучно») — отказ без эскалации:
# иначе такая фраза доходила до uncertain/модели и гасила бота эскалацией.
_CHITCHAT_RE = re.compile(
    r"(?i)\b(?:"
    r"анекдот\w*|шутк\w*|прикол\w*|"
    r"поболта\w*|развле\w*|посмея\w*"
    r")\b",
)

_CHITCHAT_REPLY = (
    "Я помогаю по продукции Hoocon и навигации по сайту — с анекдотами, "
    "увы, не ассистирую. Могу подсказать раздел сайта, документацию "
    "по артикулу или подключить менеджера."
)


def is_out_of_scope(text: str) -> bool:
    """Topic is clearly outside Hoocon HVAC scope."""
    return bool(_OUT_OF_SCOPE_RE.search(text or ""))


def triage_out_of_scope_reply(text: str) -> str | None:
    """Static refusal for non-HVAC topics."""
    if is_out_of_scope(text):
        return _OUT_OF_SCOPE_REPLY
    return None


def triage_chitchat_reply(text: str) -> str | None:
    """Polite refusal for off-topic small talk; bot stays active."""
    if _CHITCHAT_RE.search(text or ""):
        return _CHITCHAT_REPLY
    return None
