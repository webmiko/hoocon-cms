"""Static SEO routes — mirror frontend Seo titles / noindex paths.

Spec: БЗ SEO-индексация-SPA.md; docs/seo-url-migration.md (no trailing slash).
"""

from __future__ import annotations

from typing import TypedDict


class StaticRouteSeo(TypedDict, total=False):
    title: str
    description: str


SITE_NAME = "Hoocon"
DEFAULT_TITLE = "Hoocon — электроприводы вентиляции и кондиционирования"
DEFAULT_DESCRIPTION = (
    "Электроприводы для вентиляции и ОВК. Подбор модели за минуту на главной, "
    "каталог по параметрам, паспорта PDF, аналоги Belimo, запрос КП."
)
OG_IMAGE_PATH = "/og-image.png"
# Яндекс.Вебмастер — meta-тег подтверждения домена (публичный, не секрет).
YANDEX_VERIFICATION_CONTENT = "4b0c304eeaf471e0"
SLUG_RE = r"^[a-z0-9][a-z0-9-]{0,298}[a-z0-9]$|^[a-z0-9]$"

PUBLIC_STATIC_ROUTES: dict[str, StaticRouteSeo] = {
    "/": {
        "title": "Электроприводы для вентиляции и подбор",
        "description": DEFAULT_DESCRIPTION,
    },
    "/catalog": {
        "title": "Каталог электроприводов для вентиляции",
        "description": (
            "Каталог электроприводов Hoocon для вентиляции и кондиционирования. "
            "Фильтры по моменту, напряжению, типу; паспорта PDF; подбор аналогов Belimo."
        ),
    },
    "/statyi": {
        "title": "Статьи по подбору и монтажу приводов",
        "description": (
            "Подбор привода, монтаж, противопожарные и дымоудаляющие клапаны, "
            "шаровые краны и замена аналогов Belimo — для инженеров и снабжения."
        ),
    },
    "/novosti": {
        "title": "Новости продукции и поставок",
        "description": "Новости компании Hoocon: продукция, сертификаты, поставки.",
    },
    "/company": {
        "title": "О компании",
        "description": (
            "ООО «Хогон» (бренд Hoocon): производство электроприводов для вентиляции и кондиционирования."
        ),
    },
    "/zavod": {
        "title": "Заказ приводов под своим брендом",
        "description": (
            "OEM электроприводов для вентиляции и кондиционирования под вашей "
            "торговой маркой напрямую с завода Ningbo Hoocon: CE, UL, EAC. Без посредников."
        ),
    },
    "/gde-kupit": {
        "title": "Где купить электроприводы",
        "description": (
            "Прямые поставки и партнёры Hoocon по РФ; представительство завода в Беларуси — ООО «Чемпион-Тэк»."
        ),
    },
    "/dokumentaciya": {
        "title": "Документация — инструкции и паспорта PDF",
        "description": (
            "Скачайте инструкции и паспорта изделий Hoocon: поиск по SKU и семейству, "
            "PDF по одному файлу или архивом ZIP."
        ),
    },
    "/faq": {
        "title": "Ответы на частые вопросы",
        "description": (
            "Расчёт сечения, совместимость серий SA/DA, подбор крутящего момента электропривода вентиляции."
        ),
    },
    "/kontakty": {
        "title": "Контакты завода и офиса",
        "description": "Контакты ООО «Хогон»: телефон, email, адрес, реквизиты.",
    },
    "/oferta": {
        "title": "Публичная оферта",
        "description": "Публичная оферта ООО «Хогон» для юридических лиц (B2B).",
    },
    "/privacy-policy": {
        "title": "Политика обработки персональных данных",
        "description": (
            "Политика ООО «Хогон» по обработке ПДн и cookie на hoocon.ru "
            "(152-ФЗ): оператор, цели, согласия, аналитика по opt-in."
        ),
    },
    "/terms": {
        "title": "Согласие на обработку ПДн",
        "description": "Согласие на обработку персональных данных при заявках с сайта.",
    },
}

NOINDEX_PREFIXES: tuple[str, ...] = (
    "/search",
    "/consultation",
    "/rfq",
    "/replacement",
    "/compare",
    # Real screens that must stay open. They are not leftovers of a deleted page.
    "/login",
    "/register",
    "/account",
    "/kp",
)

# Old addresses that still resolve as their own pages. Server 301, not a second canonical.
CANONICAL_REPLACEMENTS: dict[str, str] = {
    "/o-kompanii": "/company",
    "/privacy": "/privacy-policy",
}
