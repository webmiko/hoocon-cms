"""Tests for Django Admin with django-unfold (Hoocon branding)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from unfold.admin import ModelAdmin

from catalog.admin import SKUAdmin
from leads.admin import LeadAdmin

User = get_user_model()

_EXTRAS_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css"


@pytest.mark.django_db
def test_admin_index_uses_unfold_and_hoocon_branding() -> None:
    """Logged-in admin index loads Unfold shell, extras, and Hoocon branding."""
    admin_user = User.objects.create_superuser(
        username="admin-styles",
        email="admin-styles@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)

    response = client.get("/admin/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "unfold" in html.lower()
    assert "hoocon-unfold-extras.css" in html
    assert "hoocon-admin-leads-sticker.js" in html
    assert "hoocon-admin-tables.js" in html
    assert "hoocon-admin.css" not in html
    assert "hoocon-admin-overrides.css" not in html
    assert "Hoocon" in html
    assert 'href="/"' in html
    # Sidebar navigation includes leads entry (badge when count > 0).
    assert "/admin/leads/lead/" in html


@pytest.mark.django_db
def test_lead_sticker_visible_on_changelist_not_only_index() -> None:
    """Sticker must survive Unfold change_list (nav-global-side = object-tools)."""
    from leads.models import Lead

    Lead.objects.create(
        name="Changelist sticker",
        email="changelist-sticker@example.com",
        message="Нужен КП — проверка sticker на changelist.",
    )
    admin_user = User.objects.create_superuser(
        username="admin-sticker-cl",
        email="admin-sticker-cl@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/leads/lead/").content.decode()
    assert "hoocon-admin-lead-sticker" in html
    assert "data-hoocon-new-leads-count" in html
    assert "hoocon-admin-support-sticker" in html
    assert "data-hoocon-support-unread-count" in html
    assert "hoocon-admin-leads-sticker.js" in html


@pytest.mark.django_db
def test_sidebar_hides_leads_without_view_permission() -> None:
    """Staff without leads.view_lead must not see Заявки in Unfold sidebar."""
    staff = User.objects.create_user(
        username="staff-noperm-nav",
        email="staff-noperm-nav@example.com",
        password="password12",
        is_staff=True,
    )
    client = Client()
    client.force_login(staff)
    html = client.get("/admin/").content.decode()
    assert 'href="/admin/leads/lead/"' not in html
    assert "hoocon-admin-lead-sticker" not in html


@pytest.mark.django_db
def test_lead_stats_page_renders_in_content_breadcrumbs() -> None:
    """Stats page breadcrumbs live in content (Unfold has no breadcrumbs block)."""
    admin_user = User.objects.create_superuser(
        username="admin-stats-bc",
        email="admin-stats-bc@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/leads/lead/stats/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-admin-breadcrumbs" in html
    assert "Статистика" in html


@pytest.mark.django_db
def test_admin_phone_shell_assets_and_markup() -> None:
    """Phone shell CSS/JS and bottom-nav markup ship on authenticated Admin."""
    admin_user = User.objects.create_superuser(
        username="admin-phone-shell",
        email="admin-phone-shell@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "hoocon-admin-phone.css" in html
    assert "hoocon-admin-phone-shell.js" in html
    assert 'id="hoocon-phone-shell"' in html
    assert 'id="hoocon-phone-shell-template"' in html
    assert "hoocon-phone-tabs" in html
    assert 'data-hoocon-phone-tab="leads"' in html
    assert 'data-hoocon-phone-tab="chat"' in html
    assert 'data-hoocon-phone-tab="clients"' in html
    assert "data-hoocon-phone-more-open" in html
    assert 'id="hoocon-phone-more"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "viewport-fit=cover" in html

    phone_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-phone.css").read_text(
        encoding="utf-8"
    )
    assert "hoocon-phone-tabs" in phone_css
    assert "hoocon-phone-select-mode" in phone_css
    assert "safe-area-inset-bottom" in phone_css

    phone_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-shell.js").read_text(
        encoding="utf-8"
    )
    assert "hoocon-phone-ready" in phone_js
    assert "max-width: 767px" in phone_js

    badges_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-live-badges.js").read_text(
        encoding="utf-8"
    )
    assert "data-hoocon-phone-leads-badge" in badges_js
    assert "data-hoocon-phone-support-badge" in badges_js


@pytest.mark.django_db
def test_admin_phone_shell_hidden_without_staff_perms() -> None:
    """Staff without lead/chat/crm perms still get «Ещё» tab only."""
    staff = User.objects.create_user(
        username="staff-phone-empty",
        email="staff-phone-empty@example.com",
        password="password12",
        is_staff=True,
    )
    client = Client()
    client.force_login(staff)
    html = client.get("/admin/").content.decode()
    assert 'id="hoocon-phone-shell"' in html
    assert 'data-hoocon-phone-tab="leads"' not in html
    assert "data-hoocon-phone-more-open" in html


@pytest.mark.django_db
def test_admin_login_page_loads_unfold() -> None:
    """Login page renders Unfold without the legacy hoocon-admin shell CSS."""
    response = Client().get("/admin/login/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-admin.css" not in html
    assert "unfold" in html.lower() or "Hoocon" in html


def test_lead_and_sku_admins_use_unfold_modeladmin() -> None:
    """LeadAdmin and SKUAdmin inherit Unfold ModelAdmin (styled forms)."""
    assert issubclass(LeadAdmin, ModelAdmin)
    assert issubclass(SKUAdmin, ModelAdmin)


def test_unfold_extras_css_covers_lead_ui() -> None:
    """Extras CSS keeps lead sticker, status tags, open button, stats layout."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    assert "--hoocon-primary: #dc1313" in css
    assert "--hoocon-primary-hover: #b01010" in css
    assert "--hoocon-primary-on-dark: #f87171" in css
    assert ".dark .hoocon-dash__panel-head a" in css
    assert ".hoocon-admin-lead-sticker" in css
    assert "hoocon-admin-lead-sticker__count" in css
    assert ".hoocon-admin-support-sticker--active" in css
    assert ".hoocon-lead-status--new" in css
    assert "a.hoocon-admin-lead-open" in css
    assert ".hoocon-lead-stats" in css
    assert ".hoocon-admin-breadcrumbs" in css
    assert ".hoocon-sidebar-rail" in css
    assert ".hoocon-sidebar-label" in css
    assert ".hoocon-nav-shell" in css
    assert ".hoocon-admin-header" in css
    assert ".hoocon-all-apps-panel" in css
    assert ".hoocon-all-apps-flyout" in css
    assert "z-index: 80" in css
    assert "min(28rem" in css
    assert ".hoocon-integrations" in css
    assert ".hoocon-integrations__actions" in css
    assert "hoocon-admin-table-stacked" in css
    assert "hoocon-admin-cell-blank" in css
    assert "hoocon-admin-card-table" in css
    assert "table.hoocon-lead-stats__table.hoocon-admin-table-stacked" in css

    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-tables.js").read_text(encoding="utf-8")
    assert "table.hoocon-lead-stats__table" in js
    assert "hoocon-phone-filter-chips" in js


@pytest.mark.django_db
def test_admin_header_is_sticky_to_top() -> None:
    """Main admin header stays pinned to the top while scrolling."""
    admin_user = User.objects.create_superuser(
        username="admin-sticky-header",
        email="admin-sticky-header@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "hoocon-admin-header" in html
    assert "sticky" in html
    assert "top-0" in html


@pytest.mark.django_db
def test_admin_sidebar_keeps_icon_rail_when_collapsed() -> None:
    """Collapsed desktop sidebar stays as a narrow icon rail (not fully hidden)."""
    admin_user = User.objects.create_superuser(
        username="admin-rail",
        email="admin-rail@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "hoocon-sidebar-rail" in html or "hoocon-sidebar-peek" in html
    assert "hoocon-nav-shell" in html
    assert "hoocon-nav-panel" in html
    assert "railWidth" in html
    assert "panelWidth" in html
    assert "sidebarPeek" in html
    assert "hoocon-sidebar-expand" not in html
    assert "isDesktopNav" in html
    assert "hoocon-sidebar-shortcut" in html
    assert "Закрыть меню" in html
    assert 'title="Панель"' in html or 'title="Панель"' in html


@pytest.mark.django_db
@override_settings(BUILD_SHA="deploysha1")
def test_admin_pwa_manifest_and_icons() -> None:
    """Admin ships a distinct PWA manifest (gray ADMIN icons, /admin/ scope)."""
    admin_user = User.objects.create_superuser(
        username="admin-pwa",
        email="admin-pwa@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "admin/img/pwa-admin-192.png?v=deploysha1" in html
    assert "apple-touch-admin.png?v=deploysha1" in html
    assert "/admin/manifest.webmanifest" in html
    assert "hoocon-admin-live-badges.js" in html
    assert "hoocon-admin-tables.js" in html
    assert "hoocon-admin-phone-shell.js" in html
    assert "hoocon-admin-phone.css" in html
    assert 'name="theme-color" content="#5a626c"' in html

    manifest = client.get("/admin/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "application/manifest+json" in manifest["Content-Type"]
    data = manifest.json()
    assert data["name"] == "Hoocon Admin"
    assert data["start_url"] == "/admin/"
    assert data["scope"] == "/admin/"
    assert data["theme_color"] == "#5a626c"
    assert data["orientation"] == "portrait-primary"
    assert any(icon["src"].endswith("pwa-admin-192.png?v=deploysha1") for icon in data["icons"])


@pytest.mark.django_db
def test_admin_login_css_prevents_ios_input_zoom() -> None:
    """Login/OTP inputs must be ≥16px so iOS Safari does not zoom on focus."""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text()
    assert "body.login input" in css
    assert "font-size: 16px !important" in css
