"""Tests for iOS Settings-style Admin phone navigation hub."""

from __future__ import annotations

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
    """Superuser hub lists dashboard row plus grouped app sections with model links."""
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
    assert "leads" in app_ids
    assert "supportchat-messages" in app_ids
    messages = next(group for group in nav["groups"] if group["id"] == "supportchat-messages")
    assert messages["action"] == "link"
    assert messages["title"] == "Сообщения"
    assert messages["url"].endswith("/admin/supportchat/conversation/")
    support = next(group for group in nav["groups"] if group["id"] == "supportchat")
    support_urls = {item["url"] for item in support["items"]}
    assert not any("/conversation/" in url for url in support_urls)
    assert not any("/message/" in url for url in support_urls)
    leads = next(group for group in nav["groups"] if group["id"] == "leads")
    assert leads["url"].endswith("?hoocon_app=leads")
    assert any(item["url"].endswith("/admin/leads/lead/") for item in leads["items"])
    section_ids = {section["id"] for section in nav["sections"]}
    assert "work" in section_ids


@pytest.mark.django_db
def test_build_phone_settings_nav_scoped_for_manager() -> None:
    """Manager without catalog perms does not get catalog group in phone hub."""
    manager_group, _ = Group.objects.get_or_create(name="Менеджер")
    lead_ct = ContentType.objects.get(app_label="leads", model="lead")
    view_lead = Permission.objects.get(content_type=lead_ct, codename="view_lead")
    manager_group.permissions.add(view_lead)
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
    assert "leads" in app_ids
    assert "catalog" not in app_ids


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
    assert 'data-hoocon-settings-open="leads"' in html
    assert "data-hoocon-settings-dashboard" in html
    assert 'id="hoocon-settings-group-leads"' in html
    assert 'href="/admin/?hoocon_app=leads"' in html or "hoocon_app=leads" in html
    assert "hoocon-admin-phone-settings.js" in html
    assert "hoocon-admin-desktop-settings.js" in html
    assert 'data-hoocon-desktop-settings-select="supportchat-messages"' in html
    assert "Сообщения" in html
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
    assert 'closest("[data-hoocon-desktop-settings-select]")' not in desktop_js
    assert "showAccountPage" in desktop_js
    assert "hoocon-desktop-settings-account" in desktop_js
    assert "hoocon_view=account" not in desktop_js
    assert 'VIEW_QUERY = "hoocon_view"' in desktop_js
