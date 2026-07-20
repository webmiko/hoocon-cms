"""Tests for Django Admin modern CMS theme."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin.css"


@pytest.mark.django_db
def test_admin_index_uses_hoocon_styles() -> None:
    """Logged-in admin index loads hoocon-admin assets and branding."""
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
    assert "hoocon-admin.css" in html
    assert "hoocon-admin-overrides.css" in html
    assert "hoocon-admin-tables.js" in html
    assert "hoocon-admin-leads-sticker.js" in html
    assert "Hoocon" in html
    assert 'href="/"' in html
    assert "hoocon-admin.css?v=" in html


@pytest.mark.django_db
def test_admin_login_page_uses_hoocon_styles() -> None:
    """Login page loads theme CSS and resolves data-theme before styles."""
    response = Client().get("/admin/login/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-admin.css" in html
    assert "data-theme-mode" in html
    assert 'localStorage.getItem("theme")' in html
    script_pos = html.find('localStorage.getItem("theme")')
    css_pos = html.find("hoocon-admin.css")
    assert script_pos != -1
    assert css_pos != -1
    assert script_pos < css_pos


def test_admin_css_is_modern_cms_layout() -> None:
    """Theme uses calm CMS surfaces, system font, and generous spacing tokens."""
    css = _CSS.read_text(encoding="utf-8")
    assert "современный CMS-layout" in css
    assert "-apple-system" in css
    assert "SF Pro Text" in css
    assert "--hoocon-primary: #2563eb" in css
    assert "--hoocon-danger: #dc2626" in css
    assert "--hoocon-block-gap: 1.75rem" in css
    assert "--hoocon-inline-padding: 1.75rem" in css
    assert "backdrop-filter: none" in css
    assert "iOS 27" not in css


def test_admin_deletelink_uses_danger_color_not_primary() -> None:
    """Delete link gets danger gradient, not primary (specificity trap)."""
    css = _CSS.read_text(encoding="utf-8")
    danger_block = css.split("a.deletelink,\n.deletelink,", 1)[1].split("}", 1)[0]
    assert "var(--hoocon-danger)" in danger_block
    assert "var(--hoocon-primary)" not in danger_block
    assert "background-image: none" in danger_block


def test_admin_tables_js_uses_hoocon_card_class() -> None:
    """Tables JS adds card class and stacks when table cannot fit width."""
    js_path = Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-tables.js"
    js = js_path.read_text(encoding="utf-8")
    assert "hoocon-admin-card-table" in js
    assert "hoocon-admin-table-stacked" in js
    assert "enableStackedCardNavigation" in js
    assert 'STACK_MQ = "(max-width: 767px)"' in js
    assert "measureNaturalTableWidth" in js
    assert "measureComfortableTableWidth" in js
    assert "MIN_DATA_COL_PX" in js
    assert "max-content" in js
    assert "ResizeObserver" in js
    assert "collapseIdleFilters" in js
    assert "enhanceSidebarActionTitles" in js
    assert "lms-admin" not in js


def test_admin_css_dashboard_uses_compact_rows_not_cards() -> None:
    """Dashboard model lists stay horizontal rows; no block card stack at 1024px."""
    css = _CSS.read_text(encoding="utf-8")
    assert "#content-main .module table thead" in css
    assert "display: none" in css.split("#content-main .module table thead", 1)[1].split("}", 1)[0]
    assert ".dashboard #content-main .module table tr {" not in css
    overrides = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-overrides.css").read_text(
        encoding="utf-8"
    )
    assert "html body #content-main .module table tbody tr" in overrides
    assert "display: flex !important" in overrides


def test_admin_css_tables_avoid_horizontal_scroll() -> None:
    """Changelist tables wrap/clip instead of overflow-x scroll."""
    css = _CSS.read_text(encoding="utf-8")
    results = css.split("#changelist-form .results {", 1)[1].split("}", 1)[0]
    assert "overflow-x: clip !important" in results
    assert "table-layout: fixed" in css
    assert "hoocon-admin-table-stacked" in css
    assert "overflow-wrap: anywhere" in css
    assert "flex-direction: column" in css
    assert "minmax(5.5rem, 32%)" in css
    assert "#changelist table .field-name" in css


def test_admin_theme_js_resolves_auto_to_light_or_dark() -> None:
    """Custom theme.js keeps data-theme as resolved light|dark (not auto)."""
    js_path = Path(__file__).resolve().parents[1] / "static/admin/js/theme.js"
    js = js_path.read_text(encoding="utf-8")
    assert "dataset.themeMode" in js
    assert "resolveTheme" in js
    assert "dataset.theme = resolveTheme(mode)" in js
