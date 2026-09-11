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
_SECTION_ORDER: tuple[str, ...] = ("", "work", "catalog", "site", "system")
_SECTION_LABELS: dict[str, str] = {
    "": "",
    "work": "Работа",
    "catalog": "Каталог",
    "site": "Сайт",
    "system": "Система",
}
_APP_SECTIONS: dict[str, str] = {
    "leads": "work",
    "crm": "work",
    "supportchat": "work",
    "supportchat-messages": "work",
    "catalog": "catalog",
    "content": "catalog",
    "analytics": "site",
    "sitesettings": "site",
    "redirects": "site",
    "social": "site",
    "webpush": "system",
    "axes": "system",
    "auth": "system",
    "django_celery_beat": "system",
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
    """One Settings row per Django app (models listed on drill-down)."""
    rows: list[dict[str, Any]] = []
    for app in admin.site.get_app_list(request):
        items: list[dict[str, str]] = []
        for model in app.get("models", []):
            admin_url = model.get("admin_url") or ""
            if not admin_url:
                continue
            items.append(
                {
                    "title": str(model.get("name") or ""),
                    "url": admin_url,
                    "add_url": str(model.get("add_url") or ""),
                },
            )
        if not items:
            continue
        app_label = str(app.get("app_label") or "")
        if app_label == "supportchat":
            messages_row = _support_messages_row(request)
            if messages_row:
                rows.append(messages_row)
            items = _supportchat_settings_items(items)
            if not items:
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
        section_key = _APP_SECTIONS.get(str(row["id"]), "system")
        buckets[section_key].append(row)

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
