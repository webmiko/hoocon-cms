"""Build iOS Settings-style phone navigation groups for Admin."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.urls import reverse

# iOS Settings–style icon tiles: (background, foreground).
_APP_ICON_STYLES: dict[str, tuple[str, str]] = {
    "home": ("#007aff", "#ffffff"),
    "leads": ("#ff9500", "#ffffff"),
    "catalog": ("#5856d6", "#ffffff"),
    "crm": ("#34c759", "#ffffff"),
    "supportchat": ("#ff2d55", "#ffffff"),
    "supportchat-messages": ("#ff2d55", "#ffffff"),
    "analytics": ("#5ac8fa", "#ffffff"),
    "sitesettings": ("#8e8e93", "#ffffff"),
    "webpush": ("#ff3b30", "#ffffff"),
    "content": ("#af52de", "#ffffff"),
    "axes": ("#ffcc00", "#1c1c1e"),
    "auth": ("#007aff", "#ffffff"),
    "django_celery_beat": ("#ff9500", "#ffffff"),
    "redirects": ("#64d2ff", "#1c1c1e"),
    "social": ("#ff6482", "#ffffff"),
}

_APP_DESCRIPTIONS: dict[str, str] = {
    "leads": "Заявки с сайта, статусы и обработка менеджерами.",
    "catalog": "Товары, артикулы, категории и медиа каталога.",
    "crm": "Клиенты, активности и работа с базой CRM.",
    "cabinet": "Заказы, спецификации и рекламации клиентского кабинета.",
    "supportchat": "FAQ чата, расписание и служебные настройки поддержки.",
    "supportchat-messages": "Входящие диалоги с сайта, Telegram и мессенджеров.",
    "analytics": "Посещаемость, страницы и сводки сайта.",
    "sitesettings": "Контакты, SEO и глобальные настройки витрины.",
    "webpush": "Подписки Web Push и рассылки.",
    "content": "Страницы, блоки и контент сайта.",
    "axes": "Безопасность входа и блокировки.",
    "auth": "Пользователи, группы и права доступа.",
    "django_celery_beat": "Периодические задачи и расписание.",
    "redirects": "Перенаправления URL и синхронизация.",
    "social": "Соцсети и маркетинговые интеграции.",
}

_APP_ICONS: dict[str, str] = {
    "leads": "inbox",
    "catalog": "inventory_2",
    "crm": "groups",
    "cabinet": "orders",
    "supportchat": "forum",
    "supportchat-messages": "chat",
    "analytics": "monitoring",
    "sitesettings": "settings",
    "webpush": "notifications",
    "content": "article",
    "axes": "shield",
    "auth": "manage_accounts",
    "django_celery_beat": "schedule",
    "redirects": "sync_alt",
    "social": "campaign",
}

# Logical iOS-style section buckets for grouped inset lists.
_SECTION_ORDER: tuple[str, ...] = ("", "work", "catalog", "content", "support", "site", "system")
_SECTION_LABELS: dict[str, str] = {
    "": "",
    "work": "Работа",
    "catalog": "Каталог",
    "content": "Контент",
    "support": "Поддержка",
    "site": "Сайт",
    "system": "Система",
}
_APP_SECTIONS: dict[str, str] = {
    "leads": "work",
    "crm": "work",
    "cabinet": "work",
    "supportchat": "support",
    "supportchat-messages": "work",
    "catalog": "catalog",
    "content": "content",
    "analytics": "site",
    "sitesettings": "site",
    "redirects": "site",
    "social": "site",
    "webpush": "site",
    "axes": "system",
    "auth": "system",
    "django_celery_beat": "system",
    "accounts": "system",
}

# Daily models lifted out of app drill-downs into flat link rows.
# Row id is always "<app_label>-<model_name>" so desktop JS can highlight it
# from the changelist path. "url_name" overrides the default changelist link.
_PROMOTED_MODELS: dict[str, tuple[dict[str, str], ...]] = {
    "leads": (
        {
            "model": "lead",
            "title": "Заявки",
            "icon": "inbox",
            "section": "work",
            "description": "Заявки с сайта, статусы и ответственные.",
            "badge": "leads",
        },
    ),
    "crm": (
        {
            "model": "client",
            "title": "Клиенты",
            "icon": "groups",
            "section": "work",
            "description": "База клиентов, карточки и контакты.",
        },
        {
            "model": "emailmessage",
            "title": "Письма",
            "icon": "mail",
            "section": "work",
            "description": "Исходящие письма и статусы доставки.",
        },
        {
            "model": "activity",
            "title": "Активности",
            "icon": "event_note",
            "section": "work",
            "description": "Звонки, задачи и заметки по клиентам.",
        },
        {
            "model": "call",
            "title": "Звонки",
            "icon": "call",
            "section": "work",
            "description": "Телефония Mango: журнал вызовов и записи разговоров.",
        },
        {
            "model": "quote",
            "title": "КП",
            "icon": "request_quote",
            "section": "work",
            "description": "Коммерческие предложения по заявкам.",
        },
        {
            "model": "clientdocument",
            "title": "Документы",
            "icon": "description",
            "section": "work",
            "description": "Файлы клиентов: счёта, УПД, спецификации.",
        },
        {
            "model": "company",
            "title": "Компании",
            "icon": "domain",
            "section": "work",
            "description": "Юрлица клиентов и их сотрудники.",
        },
    ),
    "cabinet": (
        {
            "model": "order",
            "title": "Заказы",
            "icon": "orders",
            "section": "work",
            "description": "Заказы из согласованных КП, статусы готовности.",
        },
        {
            "model": "rmacase",
            "title": "Рекламации",
            "icon": "report",
            "section": "work",
            "description": "RMA-обращения клиентов из кабинета.",
        },
    ),
    "catalog": (
        {
            "model": "sku",
            "title": "Артикулы",
            "icon": "inventory_2",
            "section": "catalog",
            "description": "Поиск по артикулам и характеристикам.",
        },
        {
            "model": "product",
            "title": "Товары",
            "icon": "deployed_code",
            "section": "catalog",
            "description": "Карточки товаров, категории и медиа.",
        },
        {
            "model": "category",
            "title": "Категории",
            "icon": "category",
            "section": "catalog",
            "description": "Дерево разделов витрины.",
        },
    ),
    "supportchat": (
        {
            "model": "faqitem",
            "title": "FAQ чата",
            "icon": "quiz",
            "section": "support",
            "description": "Частые вопросы и ответы бота.",
        },
        {
            "model": "replytemplate",
            "title": "Шаблоны ответов",
            "icon": "quick_phrases",
            "section": "support",
            "description": "Готовые ответы для менеджеров.",
        },
        {
            "model": "supportschedule",
            "title": "Расписание поддержки",
            "icon": "schedule",
            "section": "support",
            "description": "Часы работы операторов чата.",
        },
        {
            "model": "supportscheduleday",
            "title": "Дни расписания",
            "icon": "date_range",
            "section": "support",
            "description": "Исключения и особые дни расписания.",
        },
    ),
    "content": (
        {
            "model": "article",
            "title": "Статьи",
            "icon": "article",
            "section": "content",
            "description": "Статьи и материалы блога.",
        },
        {
            "model": "news",
            "title": "Новости",
            "icon": "newspaper",
            "section": "content",
            "description": "Новости компании.",
        },
        {
            "model": "page",
            "title": "Страницы",
            "icon": "description",
            "section": "content",
            "description": "Статические страницы сайта.",
        },
        {
            "model": "wikidocument",
            "title": "Вики",
            "icon": "menu_book",
            "section": "content",
            "url_name": "admin:content_wikidocument_browse",
            "description": "База знаний и инструкции для команды.",
        },
        {
            "model": "newscategory",
            "title": "Категории новостей",
            "icon": "label",
            "section": "content",
            "description": "Рубрикатор новостей.",
        },
    ),
    "sitesettings": (
        {
            "model": "sitesettings",
            "title": "Настройки сайта",
            "icon": "settings",
            "section": "site",
            "description": "Контакты, SEO и глобальные настройки витрины.",
        },
    ),
    "webpush": (
        {
            "model": "pushsubscription",
            "title": "Веб-уведомления",
            "icon": "notifications",
            "section": "site",
            "description": "Push-подписки и рассылки.",
        },
    ),
    "social": (
        {
            "model": "socialpost",
            "title": "Соцсети",
            "icon": "campaign",
            "section": "site",
            "description": "Анонсы и публикации в соцсетях.",
        },
    ),
    "redirects": (
        {
            "model": "redirect",
            "title": "Редиректы",
            "icon": "sync_alt",
            "section": "site",
            "description": "Перенаправления URL и синхронизация.",
        },
    ),
}

# Technical apps never appear in navigation for non-superusers, even when a
# group holds a technical perm (e.g. auth.view_user for assignee labels).
_SUPERUSER_ONLY_APPS: frozenset[str] = frozenset(
    {"auth", "accounts", "axes", "django_celery_beat"},
)

# Apps replaced by one custom link row (manager-facing URL ≠ model changelist).
_CUSTOM_APP_ROWS: dict[str, dict[str, str]] = {
    "analytics": {
        "id": "analytics",
        "title": "Аналитика сайта",
        "icon": "monitoring",
        "url_name": "admin:analytics_pagedailystat_stats",
        "perm": "analytics.view_pagedailystat",
        "section": "site",
        "description": "Посещаемость и страницы сайта.",
    },
}

# Extra flat link rows next to promoted models (custom views, not changelists).
_EXTRA_LINK_ROWS: dict[str, tuple[dict[str, str], ...]] = {
    "leads": (
        {
            "id": "leads-stats",
            "title": "Статистика заявок",
            "icon": "bar_chart",
            "url_name": "admin:leads_lead_stats",
            "perm": "leads.view_lead",
            "section": "work",
            "description": "SLA, воронка и обработка заявок менеджерами.",
        },
    ),
}

# Row order inside each section; rows absent from the list sink to the end.
_ROW_ORDER: dict[str, tuple[str, ...]] = {
    "work": (
        "leads-lead",
        "leads-stats",
        "supportchat-messages",
        "crm-client",
        "crm-emailmessage",
        "crm-activity",
        "crm-call",
        "crm-quote",
        "crm-clientdocument",
        "crm-company",
        "cabinet-order",
        "cabinet-rmacase",
        "cabinet-speclist",
    ),
    "catalog": (
        "catalog-sku",
        "catalog-product",
        "catalog-category",
    ),
    "content": (
        "content-article",
        "content-news",
        "content-page",
        "content-wikidocument",
        "content-newscategory",
    ),
    "support": (
        "supportchat-faqitem",
        "supportchat-replytemplate",
        "supportchat-supportschedule",
        "supportchat-supportscheduleday",
    ),
    "site": (
        "analytics",
        "sitesettings-sitesettings",
        "webpush-pushsubscription",
        "social-socialpost",
        "redirects-redirect",
    ),
}


def build_phone_settings_nav(request: HttpRequest) -> dict[str, Any] | None:
    """Grouped admin navigation for mobile Settings hub.

    Root screen: account card + iOS grouped sections with colored icon tiles.
    Tap section row → drill-down with changelist links per model.
    «Панель управления» opens the dashboard directly (no extra drill-down).
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return None

    dashboard_url = f"{reverse('admin:index')}?hoocon_view=dashboard"
    account_page_url = f"{reverse('admin:index')}?hoocon_view=account"
    home_row = _home_row(request, dashboard_url)
    app_rows = _app_rows(request)

    sections = _build_sections([home_row, *app_rows])
    groups = [row for section in sections for row in section["rows"]]

    display_name = (user.get_full_name() or "").strip() or user.get_username()
    email = (user.email or "").strip()
    initials = _initials(display_name, email)

    account_links = _account_links(request)

    return {
        "account_name": display_name,
        "account_email": email,
        "account_initials": initials,
        "sections": sections,
        "groups": groups,
        "dashboard_url": dashboard_url,
        "account_page_url": account_page_url,
        **account_links,
    }


def _account_links(request: HttpRequest) -> dict[str, str]:
    """Quick links for the account sheet (site, profile, password)."""
    user = request.user
    site_url = getattr(settings, "SITE_URL", "").strip().rstrip("/") or "/"
    links: dict[str, str] = {
        "site_url": site_url,
        "password_change_url": reverse("admin:password_change"),
        "profile_url": "",
    }
    if user.has_perm("auth.change_user") or user.has_perm("auth.view_user"):
        links["profile_url"] = reverse("admin:auth_user_change", args=[user.pk])
    return links


def _home_row(request: HttpRequest, dashboard_url: str) -> dict[str, Any]:
    """Dashboard entry — opens summary screen with alerts and KPIs."""
    subtitle = _dashboard_subtitle(request)
    return {
        "id": "home",
        "title": "Панель управления",
        "icon": "dashboard",
        "icon_bg": _APP_ICON_STYLES["home"][0],
        "icon_fg": _APP_ICON_STYLES["home"][1],
        "action": "dashboard",
        "url": dashboard_url,
        "subtitle": subtitle,
        "description": "Сводка, оповещения и последние изменения в админке.",
        "badge": "",
        "items": [],
    }


def _dashboard_subtitle(request: HttpRequest) -> str:
    """One-line preview for the dashboard row (iOS Apple-ID style)."""
    user = request.user
    parts: list[str] = []
    if user.has_perm("leads.view_lead"):
        from leads.services import count_new_leads

        unread = count_new_leads(user=user)
        if unread:
            parts.append(f"{unread} новых заявок")
    if user.has_perm("supportchat.view_conversation"):
        from supportchat.services import count_staff_unread

        support = count_staff_unread()
        if support:
            parts.append(f"{support} в поддержке")
    if not parts:
        return "Сводка, оповещения и последние изменения"
    return " · ".join(parts)


def _app_rows(request: HttpRequest) -> list[dict[str, Any]]:
    """Settings rows: promoted flat links first, app drill-downs for the rest."""
    rows: list[dict[str, Any]] = []
    is_superuser = bool(request.user.is_superuser)
    for app in admin.site.get_app_list(request):
        app_label = str(app.get("app_label") or "")
        if app_label in _SUPERUSER_ONLY_APPS and not is_superuser:
            continue
        if app_label in _CUSTOM_APP_ROWS:
            custom_row = _custom_app_row(request, app_label)
            if custom_row:
                rows.append(custom_row)
            continue
        items: list[dict[str, str]] = []
        for model in app.get("models", []):
            admin_url = model.get("admin_url") or ""
            if not admin_url:
                continue
            model_cls = model.get("model")
            model_name = str(getattr(getattr(model_cls, "_meta", None), "model_name", "") or "")
            items.append(
                {
                    "title": str(model.get("name") or ""),
                    "url": admin_url,
                    "add_url": str(model.get("add_url") or ""),
                    "model": model_name,
                },
            )
        if not items:
            continue
        if app_label == "supportchat":
            messages_row = _support_messages_row(request)
            if messages_row:
                rows.append(messages_row)
            items = _supportchat_settings_items(items)
            if not items:
                continue
        promoted, items = _promoted_rows(request, app_label, items)
        promoted.extend(_extra_link_rows(request, app_label))
        rows.extend(promoted)
        if not items:
            continue
        if len(items) == 1:
            rows.append(_leftover_link_row(app_label, items[0]))
            continue
        icon_bg, icon_fg = _APP_ICON_STYLES.get(app_label, ("#8e8e93", "#ffffff"))
        row_id = app_label or str(app.get("name") or "app")
        rows.append(
            {
                "id": row_id,
                "title": str(app.get("name") or app_label),
                "icon": _APP_ICONS.get(app_label, "folder"),
                "icon_bg": icon_bg,
                "icon_fg": icon_fg,
                "action": "drill",
                "url": f"{reverse('admin:index')}?hoocon_app={row_id}",
                "subtitle": "",
                "description": _APP_DESCRIPTIONS.get(app_label, ""),
                "badge": _badge_for_app(request, app_label),
                "items": items,
            },
        )
    return rows


def _promoted_rows(
    request: HttpRequest,
    app_label: str,
    items: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Split promoted models into flat link rows; return (rows, leftovers)."""
    spec = _PROMOTED_MODELS.get(app_label)
    if not spec:
        return [], items
    rows: list[dict[str, Any]] = []
    remaining = list(items)
    for entry in spec:
        item = next((it for it in remaining if it["model"] == entry["model"]), None)
        if item is None:
            continue
        remaining.remove(item)
        url = reverse(entry["url_name"]) if entry.get("url_name") else item["url"]
        rows.append(
            _link_row(
                request,
                row_id=f"{app_label}-{entry['model']}",
                title=entry["title"],
                icon=entry["icon"],
                style=app_label,
                url=url,
                section=entry["section"],
                description=entry.get("description", ""),
                badge=_badge_for_app(request, entry["badge"]) if entry.get("badge") else "",
            ),
        )
    return rows, remaining


def _extra_link_rows(request: HttpRequest, app_label: str) -> list[dict[str, Any]]:
    """Custom-view link rows (e.g. lead stats) alongside promoted models."""
    rows: list[dict[str, Any]] = []
    for entry in _EXTRA_LINK_ROWS.get(app_label, ()):
        if not request.user.has_perm(entry["perm"]):
            continue
        rows.append(
            _link_row(
                request,
                row_id=entry["id"],
                title=entry["title"],
                icon=entry["icon"],
                style=app_label,
                url=reverse(entry["url_name"]),
                section=entry["section"],
                description=entry.get("description", ""),
            ),
        )
    return rows


def _custom_app_row(request: HttpRequest, app_label: str) -> dict[str, Any] | None:
    """Link row for an app whose manager-facing URL is not a changelist."""
    entry = _CUSTOM_APP_ROWS[app_label]
    user = request.user
    if not user.has_perm(entry["perm"]):
        return None
    return _link_row(
        request,
        row_id=entry["id"],
        title=entry["title"],
        icon=entry["icon"],
        style=app_label,
        url=reverse(entry["url_name"]),
        section=entry["section"],
        description=entry.get("description", ""),
    )


def _leftover_link_row(app_label: str, item: dict[str, str]) -> dict[str, Any]:
    """Single leftover model: flat link instead of a one-item drill-down."""
    title = item["title"]
    return {
        "id": f"{app_label}-{item['model']}",
        "title": title[:1].upper() + title[1:] if title else title,
        "icon": _APP_ICONS.get(app_label, "folder"),
        "icon_bg": _APP_ICON_STYLES.get(app_label, ("#8e8e93", "#ffffff"))[0],
        "icon_fg": _APP_ICON_STYLES.get(app_label, ("#8e8e93", "#ffffff"))[1],
        "action": "link",
        "url": item["url"],
        "subtitle": "",
        "description": "",
        "badge": "",
        "items": [],
        "section": _APP_SECTIONS.get(app_label, "system"),
    }


def _link_row(
    request: HttpRequest,
    *,
    row_id: str,
    title: str,
    icon: str,
    style: str,
    url: str,
    section: str,
    description: str = "",
    badge: str = "",
) -> dict[str, Any]:
    """Flat direct-link row shared by promoted and custom rows."""
    del request
    icon_bg, icon_fg = _APP_ICON_STYLES.get(style, ("#8e8e93", "#ffffff"))
    return {
        "id": row_id,
        "title": title,
        "icon": icon,
        "icon_bg": icon_bg,
        "icon_fg": icon_fg,
        "action": "link",
        "url": url,
        "subtitle": "",
        "description": description,
        "badge": badge,
        "items": [],
        "section": section,
    }


def _support_messages_row(request: HttpRequest) -> dict[str, Any] | None:
    """Inbox row — direct link to conversations with unread sticker."""
    user = request.user
    if not user.has_perm("supportchat.view_conversation"):
        return None
    icon_bg, icon_fg = _APP_ICON_STYLES["supportchat-messages"]
    badge = _badge_for_support_messages(request)
    return {
        "id": "supportchat-messages",
        "title": "Сообщения",
        "icon": _APP_ICONS["supportchat-messages"],
        "icon_bg": icon_bg,
        "icon_fg": icon_fg,
        "action": "link",
        "url": reverse("admin:supportchat_conversation_changelist"),
        "subtitle": "",
        "description": _APP_DESCRIPTIONS["supportchat-messages"],
        "badge": badge,
        "items": [],
    }


def _supportchat_settings_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Support app drill-down without inbox / debug message list."""
    kept: list[dict[str, str]] = []
    for item in items:
        url = item.get("url") or ""
        if "/conversation/" in url or "/message/" in url:
            continue
        kept.append(item)
    return kept


def _badge_for_app(request: HttpRequest, app_label: str) -> str:
    """Numeric badge on root rows (leads, support) like iOS notification counts."""
    if app_label == "leads":
        from config.unfold_callbacks import badge_new_leads

        value = badge_new_leads(request)
        return str(value) if value else ""
    return ""


def _badge_for_support_messages(request: HttpRequest) -> str:
    """Unread conversations sticker for the messages row."""
    from config.unfold_callbacks import badge_support_unread

    value = badge_support_unread(request)
    return str(value) if value else ""


def _build_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket rows into iOS Settings inset groups with optional headers."""
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in _SECTION_ORDER}
    for row in rows:
        if row["id"] == "home":
            buckets[""].append(row)
            continue
        section_key = str(row.get("section") or _APP_SECTIONS.get(str(row["id"]), "system"))
        buckets.setdefault(section_key, []).append(row)

    for key, order in _ROW_ORDER.items():
        bucket = buckets.get(key)
        if not bucket:
            continue
        rank = {row_id: index for index, row_id in enumerate(order)}
        bucket.sort(key=lambda row: rank.get(str(row["id"]), len(order)))

    sections: list[dict[str, Any]] = []
    for key in _SECTION_ORDER:
        section_rows = buckets.get(key) or []
        if not section_rows:
            continue
        sections.append(
            {
                "id": key or "home",
                "label": _SECTION_LABELS.get(key, ""),
                "rows": section_rows,
            },
        )
    return sections


def _initials(display_name: str, email: str) -> str:
    parts = [p for p in display_name.replace(".", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    if email:
        return email[0].upper()
    return "?"
