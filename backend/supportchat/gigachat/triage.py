"""Cold-chat triage mode: greet, clarify intent, hand off product questions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings as dj_settings

from supportchat.gigachat.manuals_kb import extract_sku_tokens

_MODE_TRIAGE = "triage"
_MODE_FULL = "full"

_PRODUCT_KEYWORD_RE = re.compile(
    r"(?i)\b(?:"
    r"привод|заслонк|клапан|момент|артикул|подбор|аналог|belimo|"
    r"электропривод|шаровой\s+кран|овк|hvac|вентиляц|кондицион|"
    r"цена|стоимость|кп|коммерческ|счёт|счет|наличи|"
    r"da\d|sa\d|hv\d|8100"
    r")\b",
)
_EXPLICIT_MANAGER_RE = re.compile(
    r"(?i)\b(?:"
    r"менеджер\w*|оператор\w*|живой\s+человек|перезвоните|позвоните|позовите"
    r")\b",
)

_HANDOFF_PRODUCT_TEXT = (
    "Спасибо за вопрос! По подбору, характеристикам и артикулам переключаю чат на менеджера — "
    "дальше ответит человек. Можете оставить контакт или уточнить серию в сообщении."
)
_HANDOFF_MANAGER_TEXT = "Переключаю чат на менеджера — дальше ответит человек, ожидайте, пожалуйста."


@dataclass(frozen=True)
class SiteNavSection:
    """Public site path the bot may suggest in triage mode."""

    path: str
    title: str
    pattern: re.Pattern[str]
    reply: str


# Порядок: более узкие формулировки выше общих («контакты» ниже «где купить»).
SITE_NAV_SECTIONS: tuple[SiteNavSection, ...] = (
    SiteNavSection(
        path="/gde-kupit",
        title="Где купить",
        pattern=re.compile(
            r"(?i)\b(?:"
            r"где\s+купить|купить|дилер|дистрибьютор|партн[её]р|поставщик|магазин"
            r")\b",
        ),
        reply=(
            "Актуальный список дилеров и партнёров — на странице /gde-kupit. "
            "Там же OEM-поставки с завода. По индивидуальному подбору подключу менеджера."
        ),
    ),
    SiteNavSection(
        path="/consultation",
        title="Консультация",
        pattern=re.compile(
            r"(?i)\b(?:"
            r"консультац|заявк|связаться|связь|обратн\w+\s+связ"
            r")\w*\b",
        ),
        reply=(
            "Оставить заявку на консультацию инженера можно на /consultation — "
            "ответим в рабочее время. Или напишите здесь, что хотите уточнить."
        ),
    ),
    SiteNavSection(
        path="/kontakty",
        title="Контакты",
        pattern=re.compile(
            r"(?i)\b(?:"
            r"контакт|телефон|позвонить|адрес|email|e-mail|почт[аы]|реквизит"
            r")\w*\b",
        ),
        reply=(
            "Телефоны, адрес и реквизиты — на /kontakty. "
            "Для вопроса по оборудованию могу также подключить менеджера в этом чате."
        ),
    ),
    SiteNavSection(
        path="/catalog",
        title="Каталог",
        pattern=re.compile(
            r"(?i)\b(?:"
            r"каталог|ассортимент|линейк|сери[ия]\s+da|сери[ия]\s+sa|сери[ия]\s+hv"
            r")\w*\b",
        ),
        reply=(
            "Каталог приводов и комплектующих — /catalog: фильтры по моменту, напряжению "
            "и типу клапана. По подбору под вашу задачу лучше подключить менеджера."
        ),
    ),
    SiteNavSection(
        path="/faq",
        title="Вопросы и ответы",
        pattern=re.compile(
            r"(?i)\b(?:"
            r"faq|частые\s+вопрос|вопросы\s+и\s+ответ"
            r")\b",
        ),
        reply="Ответы на частые вопросы — в разделе /faq на сайте.",
    ),
    SiteNavSection(
        path="/zavod",
        title="OEM · завод",
        pattern=re.compile(r"(?i)\b(?:завод|oem|производств|изготовлени)\w*\b"),
        reply=(
            "Поставки OEM и сотрудничество с заводом — страница /zavod. Можно оставить заявку там или написать здесь."
        ),
    ),
    SiteNavSection(
        path="/company",
        title="О компании",
        pattern=re.compile(r"(?i)\b(?:о\s+компани|компани[ия]\s+hoocon|hoocon)\b"),
        reply="Кратко о компании Hoocon — на /company.",
    ),
    SiteNavSection(
        path="/rfq",
        title="Запрос цены",
        pattern=re.compile(r"(?i)\b(?:запрос\s+цен|коммерческ\w+\s+предлож)\w*\b"),
        reply=(
            "Форма запроса коммерческого предложения — /rfq. "
            "Или подключу менеджера в этом чате — напишите, что нужно подобрать."
        ),
    ),
)


def gigachat_mode() -> str:
    """``triage`` (cold chat) or ``full`` (KB answers)."""
    raw = getattr(dj_settings, "GIGACHAT_MODE", _MODE_TRIAGE).strip().casefold()
    if raw == _MODE_FULL:
        return _MODE_FULL
    return _MODE_TRIAGE


def is_triage_mode() -> bool:
    return gigachat_mode() == _MODE_TRIAGE


def is_product_intent(text: str) -> bool:
    """User message is about products, specs, pricing, or selection."""
    body = (text or "").strip()
    if not body:
        return False
    if extract_sku_tokens(body):
        return True
    if _PRODUCT_KEYWORD_RE.search(body):
        return True
    return False


def wants_manager(text: str) -> bool:
    """User explicitly asks for a human."""
    return bool(_EXPLICIT_MANAGER_RE.search(text or ""))


def triage_site_nav_reply(text: str) -> str | None:
    """Suggest a site section when the user asks about contacts, catalog, etc."""
    body = (text or "").strip()
    if not body:
        return None
    for section in SITE_NAV_SECTIONS:
        if section.pattern.search(body):
            return section.reply
    return None


def triage_site_nav_prompt_block() -> str:
    """Navigation cheat sheet for the triage system prompt."""
    lines = ["## Разделы сайта (можно советовать без [ESCALATE])"]
    for section in SITE_NAV_SECTIONS:
        lines.append(f"- {section.title} → {section.path}")
    lines.append("- Документация → /dokumentaciya (с артикулом: /dokumentaciya?q=DA2MU24)")
    lines.append("- Квиз подбора на главной → /#podbor")
    lines.append(
        "Давай путь в ответе. Не выдумывай других URL. "
        "Паспорт/инструкция на модель — ссылка на /dokumentaciya?q=…, не подбор привода."
    )
    return "\n".join(lines)


def triage_clarification_prompt_block() -> str:
    """How to qualify product requests before handoff to a manager."""
    return """\
## Уточнение перед менеджером (важно)
Если клиент спрашивает про продукцию, подбор, цену, КП, артикул или характеристики:
1. **Не консультируй**: не называй серии DA/SA/HV, артикулы, моменты, «рекомендуем модель».
   Не используй формат ``## [manual.…]`` — его нет в этом режиме.
2. Задай **1–2 уточняющих вопроса** (тип арматуры, площадь/диаметр, перепад/расход,
   напряжение 24/230 В, fail-safe, количество) — только то, чего нет в переписке.
3. Можно без [ESCALATE] посоветовать категорию каталога или квиз /#podbor на главной.
4. Не подбирай конкретную модель по площади заслонки — это делает менеджер или квиз.
5. После ответа клиента на уточнение — [ESCALATE] с строкой «Для менеджера: …» (факты из чата)."""


_MANAGER_SUMMARY_RE = re.compile(
    r"(?:для менеджера|передал менеджеру|менеджеру)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_triage_escalation_note(text: str) -> str:
    """Extract manager handoff summary from bot reply."""
    body = (text or "").strip()
    if not body:
        return ""
    match = _MANAGER_SUMMARY_RE.search(body)
    if match:
        return match.group(1).strip()[:500]
    return ""


def triage_handoff_reply(text: str) -> tuple[str, str]:
    """Static handoff message and escalation note for triage mode."""
    if wants_manager(text):
        return _HANDOFF_MANAGER_TEXT, "Клиент просит менеджера."
    return _HANDOFF_PRODUCT_TEXT, "Вопрос о продукции (режим первичного приёма)."
