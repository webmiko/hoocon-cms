"""Tests for iOS Settings-style Admin phone navigation hub."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from config.phone_settings_nav import build_phone_settings_nav

User = get_user_model()

_PHONE_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-phone.css"
_PHONE_JS = Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-settings.js"


@pytest.mark.django_db
def test_build_phone_settings_nav_groups_apps_for_superuser() -> None:
    """Superuser hub lists dashboard row plus grouped sections with flat links."""
    admin_user = User.objects.create_superuser(
        username="settings-nav-su",
        email="settings-nav-su@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    nav = build_phone_settings_nav(request)
    assert nav is not None
    assert nav["account_name"]
    assert nav["site_url"]
    assert nav["password_change_url"] == reverse("admin:password_change")
    assert nav["profile_url"] == reverse("admin:auth_user_change", args=[admin_user.pk])
    assert nav["account_page_url"].endswith("?hoocon_view=account")
    home = nav["groups"][0]
    assert home["id"] == "home"
    assert home["action"] == "dashboard"
    assert home["url"].endswith("?hoocon_view=dashboard")
    assert home["icon_bg"] == "#007aff"
    app_ids = {group["id"] for group in nav["groups"]}
    assert "supportchat-messages" in app_ids
    # Daily sections are flat link rows — no drill-down to reach them.
    messages = next(group for group in nav["groups"] if group["id"] == "supportchat-messages")
    assert messages["action"] == "link"
    assert messages["title"] == "Сообщения"
    assert messages["url"].endswith("/admin/supportchat/conversation/")
    leads = next(group for group in nav["groups"] if group["id"] == "leads-lead")
    assert leads["action"] == "link"
    assert leads["url"].endswith("/admin/leads/lead/")
    assert leads["title"] == "Заявки"
    section_ids = {section["id"] for section in nav["sections"]}
    assert "work" in section_ids
    assert "catalog" in section_ids
    assert "support" in section_ids
    assert "system" in section_ids


@pytest.mark.django_db
def test_build_phone_settings_nav_flattened_daily_rows() -> None:
    """Daily sections expose direct links; leftover models stay in drill-downs."""
    admin_user = User.objects.create_superuser(
        username="settings-nav-flat",
        email="settings-nav-flat@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    nav = build_phone_settings_nav(request)
    assert nav is not None
    groups = {group["id"]: group for group in nav["groups"]}

    # «Работа» — one tap to every daily section, in fixed order.
    work = next(section for section in nav["sections"] if section["id"] == "work")
    work_ids = [row["id"] for row in work["rows"]]
    assert work_ids[:7] == [
        "leads-lead",
        "leads-stats",
        "supportchat-messages",
        "crm-client",
        "crm-emailmessage",
        "crm-activity",
        "crm-quote",
    ]
    assert groups["leads-stats"]["action"] == "link"
    assert groups["leads-stats"]["url"].endswith("/admin/leads/lead/stats/")
    assert groups["crm-client"]["url"].endswith("/admin/crm/client/")
    assert groups["crm-emailmessage"]["url"].endswith("/admin/crm/emailmessage/")
    assert groups["crm-quote"]["url"].endswith("/admin/crm/quote/")

    # Остальные модели crm (шаблоны писем, вложения, состояние ящика) —
    # в drill-строке «crm», не плоско.
    assert groups["crm"]["action"] == "drill"
    crm_items = {item["url"] for item in groups["crm"]["items"]}
    assert any("/emailtemplate/" in url for url in crm_items)
    assert any("/emailattachment/" in url for url in crm_items)
    assert any("/inboundmailboxstate/" in url for url in crm_items)
    assert "leads" not in groups

    # «Каталог» — top models flat, справочники remain inside the drill row.
    assert groups["catalog-sku"]["url"].endswith("/admin/catalog/sku/")
    catalog_items = {item["url"] for item in groups["catalog"]["items"]}
    assert not any("/sku/" in url for url in catalog_items)
    assert not any("/product/" in url or "/category/" in url for url in catalog_items)
    assert any("/attribute/" in url for url in catalog_items)

    # «Поддержка» — все разделы чата плоско; drill-строки supportchat нет.
    assert "supportchat" not in groups
    assert groups["supportchat-faqitem"]["action"] == "link"
    assert groups["supportchat-faqitem"]["url"].endswith("/admin/supportchat/faqitem/")

    # Контент — плоские ссылки; Вики ведёт на browse-страницу, не changelist.
    assert groups["content-wikidocument"]["url"].endswith("/admin/content/wikidocument/browse/")
    assert "content" not in groups

    # «Система» остаётся drill-down для технических приложений.
    assert groups["axes"]["action"] == "drill"
    assert groups["auth"]["action"] == "drill"


@pytest.mark.django_db
def test_build_phone_settings_nav_scoped_for_manager() -> None:
    """Manager without catalog perms does not get catalog group in phone hub."""
    manager_group, _ = Group.objects.get_or_create(name="Менеджер")
    lead_ct = ContentType.objects.get(app_label="leads", model="lead")
    view_lead = Permission.objects.get(content_type=lead_ct, codename="view_lead")
    manager_group.permissions.set([view_lead])
    manager = User.objects.create_user(
        username="settings-nav-mgr",
        email="settings-nav-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    manager.groups.add(manager_group)
    request = RequestFactory().get("/admin/")
    request.user = manager
    nav = build_phone_settings_nav(request)
    assert nav is not None
    app_ids = {group["id"] for group in nav["groups"]}
    assert "leads-lead" in app_ids
    assert "catalog" not in app_ids
    assert "catalog-sku" not in app_ids


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
def test_admin_index_includes_phone_settings_hub_markup() -> None:
    """Admin index ships iOS Settings hub markup and drill-down script."""
    admin_user = User.objects.create_superuser(
        username="settings-nav-html",
        email="settings-nav-html@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "data-hoocon-phone-settings" in html
    # Каталог остаётся drill-down для справочников; заявки — плоская ссылка.
    assert 'data-hoocon-settings-open="catalog"' in html
    assert 'id="hoocon-settings-group-catalog"' in html
    assert "hoocon_app=catalog" in html
    assert 'data-hoocon-desktop-settings-select="leads-lead"' in html
    assert 'href="/admin/leads/lead/"' in html
    assert "data-hoocon-settings-dashboard" in html
    assert "hoocon-admin-phone-settings.js" in html
    assert "hoocon-admin-desktop-settings.js" in html
    assert 'data-hoocon-desktop-settings-select="supportchat-messages"' in html
    assert "Сообщения" in html
    # Блок «Разделы» на дашборде — плитки групп из той же навигационной спеки.
    assert "hoocon-nav-sections" in html
    assert "Разделы" in html
    assert "data-hoocon-settings-header-back" in html
    assert 'id="hoocon-desktop-settings-account"' in html
    assert "hoocon_view=account" in html
    assert 'data-hoocon-desktop-settings-select="account"' in html
    assert 'id="hoocon-phone-settings-account-page"' in html
    assert "hoocon-phone-settings__account-page" in html
    assert "hoocon-phone-settings__account-links" in html
    assert "Открыть сайт" in html
    assert "Изменить пароль" in html
    assert "Профиль учётной записи" in html
    assert reverse("admin:password_change") in html
    assert reverse("admin:auth_user_change", args=[admin_user.pk]) in html
    assert "hoocon-phone-settings-dashboard-content" in html
    assert "hoocon-phone-settings__icon-tile" in html
    assert "hoocon-phone-settings__section-label" in html


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
def test_changelist_includes_desktop_account_nav_link() -> None:
    """Desktop sidebar links to account page instead of a modal sheet."""
    admin_user = User.objects.create_superuser(
        username="settings-nav-changelist",
        email="settings-nav-changelist@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/supportchat/faqitem/").content.decode()
    assert 'data-hoocon-desktop-settings-select="account"' in html
    assert "hoocon_view=account" in html
    assert 'id="hoocon-phone-settings-account"' not in html


def _sidebar_hrefs(html: str) -> dict[str, str]:
    """Parse desktop sidebar row id → href from rendered admin HTML."""
    found: dict[str, str] = {}
    for match in re.finditer(
        r'<a\s+([^>]*data-hoocon-desktop-settings-select="([^"]+)"[^>]*)>',
        html,
        flags=re.IGNORECASE,
    ):
        attrs, row_id = match.group(1), match.group(2)
        href_match = re.search(r'href="([^"]+)"', attrs)
        if href_match:
            found[row_id] = href_match.group(1)
    for match in re.finditer(
        r'<a\s+([^>]*href="([^"]+)"[^>]*data-hoocon-desktop-settings-select="([^"]+)"[^>]*)>',
        html,
        flags=re.IGNORECASE,
    ):
        found[match.group(3)] = match.group(2)
    return found


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
def test_desktop_sidebar_links_match_nav_on_index_and_changelists() -> None:
    """Sidebar hrefs are stable on /admin/ and changelist pages (OS27 split-pane nav)."""
    admin_user = User.objects.create_superuser(
        username="settings-nav-links",
        email="settings-nav-links@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    nav = build_phone_settings_nav(request)
    assert nav is not None
    expected = {group["id"]: group["url"] for group in nav["groups"]}
    expected["account"] = nav["account_page_url"]

    client = Client()
    client.force_login(admin_user)
    for path in (
        "/admin/",
        "/admin/catalog/sku/",
        "/admin/leads/lead/",
        reverse("admin:supportchat_conversation_changelist"),
    ):
        html = client.get(path).content.decode()
        sidebar = _sidebar_hrefs(html)
        for row_id, url in expected.items():
            assert sidebar.get(row_id) == url, f"{path}: {row_id}"

    leads = next(group for group in nav["groups"] if group["id"] == "leads-lead")
    assert leads["action"] == "link"
    assert leads["url"].endswith("/admin/leads/lead/")
    messages = next(group for group in nav["groups"] if group["id"] == "supportchat-messages")
    assert messages["url"] == reverse("admin:supportchat_conversation_changelist")


def test_phone_settings_loaded_surface_css_and_js() -> None:
    """Phone Settings hub styles and drill-down live in loaded admin assets."""
    css = _PHONE_CSS.read_text(encoding="utf-8")
    js = _PHONE_JS.read_text(encoding="utf-8")
    assert "hoocon-phone-settings-hub" in css
    assert "color: var(--os27-accent" in css.split(".hoocon-phone-settings-back")[1].split("}")[0]
    assert 'html.dark body.hoocon-phone-ready .hoocon-phone-header-menu__btn[aria-expanded="true"]' in css
    assert (
        "var(--hoocon-primary-on-dark"
        in css.split('html.dark body.hoocon-phone-ready .hoocon-phone-header-menu__btn[aria-expanded="true"]')[
            1
        ].split("}")[0]
    )
    assert "hoocon-phone-settings__icon-tile" in css
    assert "hoocon-phone-settings__badge" in css
    assert "hoocon-phone-ready .hoocon-admin-header .container" in css
    assert "display: none !important" in css.split("hoocon-phone-settings-hub .hoocon-phone-shell")[1]

    os27_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-os27.css").read_text(encoding="utf-8")
    assert "hoocon-phone-ready #content.container" in os27_css
    assert "padding-inline: var(--hoocon-phone-edge-inset, 0.5rem) !important" in os27_css
    assert (
        "border-radius: var(--hoocon-radius)"
        in os27_css.split("body.hoocon-os27.hoocon-phone-ready .hoocon-os27-group")[1].split("}")[0]
    )
    assert "hoocon-desktop-settings-detail__hero" in os27_css
    assert "hoocon-desktop-settings-account" in os27_css
    desktop_account_link = (
        "hoocon-desktop-settings-account__panel "
        ".hoocon-phone-settings__account-links .hoocon-phone-settings__row--link"
    )
    assert desktop_account_link in os27_css
    assert "padding: 0.7rem 1rem" in os27_css
    assert "hoocon-phone-settings__account-page" in css
    assert "hoocon-phone-settings__account-links" in css
    assert "hoocon-phone-settings-account" in css
    account_page_rule = css.split(".hoocon-phone-settings__account-page .hoocon-phone-settings__account-links")[
        1
    ].split("}")[0]
    assert "border-radius: var(--hoocon-radius)" in account_page_rule
    assert (
        "padding: 0.7rem 1rem"
        in css.split(
            ".hoocon-phone-settings__account-page .hoocon-phone-settings__account-links "
            ".hoocon-phone-settings__row--link"
        )[1].split("}")[0]
    )
    assert ".hoocon-phone-settings__account-page .hoocon-phone-settings__account-theme > div" in css
    assert (
        "border: none !important"
        in css.split(".hoocon-phone-settings__account-page .hoocon-phone-settings__account-theme > div")[1].split("}")[
            0
        ]
    )
    assert "openAccountPage" in js
    assert "data-hoocon-settings-open" in js
    assert "data-hoocon-settings-dashboard" in js
    assert "hoocon-phone-settings-detail" in js
    assert "hoocon_view=dashboard" in js

    desktop_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-desktop-settings.js").read_text(
        encoding="utf-8"
    )
    assert "data-hoocon-desktop-settings-select" in desktop_js
    assert "hoocon-desktop-settings-app" in desktop_js
    assert "hoocon_app" in desktop_js
    assert "supportchat-messages" in desktop_js
    assert "activeNavIdFromPath" in desktop_js
    assert 'DESKTOP_MQ = "(min-width: 768px)"' in desktop_js
    assert "navigateToFirstAppModel" in desktop_js
    assert 'closest("[data-hoocon-desktop-settings-select]")' not in desktop_js
    assert "showAccountPage" in desktop_js
    assert "hoocon-desktop-settings-account" in desktop_js
    assert "hoocon_view=account" not in desktop_js
    assert 'VIEW_QUERY = "hoocon_view"' in desktop_js


@pytest.mark.django_db
def test_command_palette_configured_for_manager_models() -> None:
    """Ctrl+K palette searches manager-facing records, not technical tables."""
    from django.conf import settings

    command = settings.UNFOLD.get("COMMAND") or {}
    models = command.get("search_models") or []
    assert command.get("show_history") is True
    for expected in (
        "leads.lead",
        "supportchat.conversation",
        "crm.client",
        "catalog.sku",
    ):
        assert expected in models
    # Технические модели вне whitelist.
    assert "axes.accesslog" not in models
    assert "supportchat.message" not in models


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
def test_command_search_endpoint_finds_lead_record() -> None:
    """/admin/search/ returns a direct link to a matching lead for staff."""
    from leads.models import Lead

    admin_user = User.objects.create_superuser(
        username="settings-nav-search",
        email="settings-nav-search@example.com",
        password="password12",
    )
    lead = Lead.objects.create(name="Палитра Поисков", company="Hoocon")
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/search/", {"s": "Палитра Поисков"})
    assert response.status_code == 200
    html = response.content.decode()
    assert "Палитра Поисков" in html
    assert f"/admin/leads/lead/{lead.pk}/" in html


def test_nav_sections_tiles_css_loaded_surface() -> None:
    """«Разделы» tiles styles live in the loaded os27 stylesheet."""
    os27_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-os27.css").read_text(encoding="utf-8")
    assert ".hoocon-nav-sections__grid" in os27_css
    grid_rule = os27_css.split(".hoocon-nav-sections__grid")[1].split("}")[0]
    assert "display: grid" in grid_rule
    link_rule = os27_css.split(".hoocon-nav-sections__link {")[1].split("}")[0]
    assert "display: flex" in link_rule


def _nav_for_group(username: str, group_name: str) -> dict:
    """Build nav for a staff user belonging to a named staff group."""
    from accounts.services import ensure_staff_groups

    ensure_staff_groups()
    group = Group.objects.get(name=group_name)
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
    )
    user.groups.add(group)
    request = RequestFactory().get("/admin/")
    request.user = user
    nav = build_phone_settings_nav(request)
    assert nav is not None
    return nav


@pytest.mark.django_db
def test_manager_nav_shows_only_permitted_sections() -> None:
    """«Менеджер»: плоские ссылки только по его пермишенам, «Система» скрыта."""
    nav = _nav_for_group("nav-mgr", "Менеджер")
    ids = {row["id"] for row in nav["groups"]}
    # Ежедневные ссылки менеджера.
    assert {
        "leads-lead",
        "supportchat-messages",
        "crm-client",
        "crm-emailmessage",
        "crm-activity",
        "crm-quote",
        "crm-clientdocument",
        "crm-company",
        "cabinet-order",
        "cabinet-rmacase",
        "cabinet-speclist",
    } <= ids
    # Шаблоны писем — единственный непиннед остаток CRM у менеджера:
    # рендерится плоской строкой, а не drill-разделом.
    assert "crm-emailtemplate" in ids
    assert "crm" not in ids
    # Каталог — view-only по матрице, но ссылки видны.
    assert {"catalog-sku", "catalog-product", "catalog-category", "catalog"} <= ids
    # Аналитика и веб-пуш по матрице доступны.
    assert {"analytics", "webpush-pushsubscription"} <= ids
    # Нет доступа — нет строки и нет пустой секции.
    forbidden = {
        "auth",
        "auth-user",
        "axes",
        "django_celery_beat",
        "accounts",
        "sitesettings-sitesettings",
        "social-socialpost",
        "redirects-redirect",
        "supportchat-faqitem",
        "supportchat-replytemplate",
        "leads-companymanagerrule",
        "content-article",
        "content-news",
        "content-page",
        "content-wikidocument",
        "content-newscategory",
    }
    assert not (forbidden & ids)
    section_ids = {section["id"] for section in nav["sections"]}
    assert "system" not in section_ids
    assert "content" not in section_ids


@pytest.mark.django_db
def test_admin_group_nav_excludes_superuser_only_apps() -> None:
    """«Админ» видит контент/настройки, но auth/axes/celery — только суперюзеру."""
    nav = _nav_for_group("nav-owner", "Админ")
    ids = {row["id"] for row in nav["groups"]}
    assert {
        "content-article",
        "content-news",
        "content-page",
        "sitesettings-sitesettings",
        "social-socialpost",
        "redirects-redirect",
    } <= ids
    # Группа «Админ» — не суперюзер: технические приложения скрыты из навигации,
    # хотя auth.view_user есть у всех групп для подписей ответственных.
    assert not ({"auth", "auth-user", "axes", "django_celery_beat"} & ids)
    # FAQ/шаблоны бота и вики не входят в матрицу группы.
    assert not ({"supportchat-faqitem", "supportchat-replytemplate", "content-wikidocument"} & ids)


@pytest.mark.django_db
def test_analyst_nav_matches_manager_surface() -> None:
    """«Аналитик» — тот же набор ссылок, что у менеджера (view-only)."""
    nav = _nav_for_group("nav-analyst", "Аналитик")
    ids = {row["id"] for row in nav["groups"]}
    assert {
        "leads-lead",
        "supportchat-messages",
        "crm-client",
        "catalog-sku",
        "analytics",
        "webpush-pushsubscription",
    } <= ids
    assert not ({"auth-user", "axes", "sitesettings-sitesettings"} & ids)
    section_ids = {section["id"] for section in nav["sections"]}
    assert "system" not in section_ids
