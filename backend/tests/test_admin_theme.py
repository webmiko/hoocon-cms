"""Tests for Django Admin with django-unfold (Hoocon branding)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from unfold.admin import ModelAdmin

from catalog.admin import SKUAdmin
from leads.admin import LeadAdmin

User = get_user_model()

_EXTRAS_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css"
_OS27_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-os27.css"


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
    assert "hoocon-os27.css" in html
    assert "hoocon-unfold-extras.css" in html
    assert "hoocon-os27" in html
    extras_pos = html.index("hoocon-unfold-extras.css")
    os27_pos = html.index("hoocon-os27.css")
    assert os27_pos > extras_pos, "OS27 must load after unfold-extras to win cascade"
    assert "hoocon-admin-leads-sticker.js" in html
    assert "hoocon-admin-tables.js" in html
    assert "hoocon-admin.css" not in html
    assert "hoocon-admin-overrides.css" not in html
    assert "Hoocon" in html
    assert 'href="/"' in html
    # Sidebar navigation includes leads entry (badge when count > 0).
    assert "/admin/leads/lead/" in html


def test_sidebar_active_item_keeps_default_text_color() -> None:
    """Selected sidebar rows tint background only — label color must not switch to accent."""
    os27_css = _OS27_CSS.read_text(encoding="utf-8")
    app_list = (Path(__file__).resolve().parents[1] / "templates/unfold/helpers/app_list.html").read_text(
        encoding="utf-8"
    )

    active_row_rule = os27_css.split("body.hoocon-os27 .hoocon-desktop-settings-sidebar__row.is-active")[1].split("}")[
        0
    ]
    assert "background: var(--os27-accent-soft)" in active_row_rule
    assert "color: var(--os27-accent)" not in active_row_rule

    nav_active_rule = os27_css.split('body.hoocon-os27 #nav-sidebar-apps a[class*="bg-primary"]')[1].split("}")[0]
    assert "background: var(--os27-accent-soft)" in nav_active_rule
    assert "color: var(--os27-accent)" not in nav_active_rule

    assert "color: inherit !important" in os27_css
    assert "selection tint on background only" in os27_css

    assert "item.active %}bg-base-100 font-semibold dark:bg-white/[.06] active" in app_list
    assert "text-primary-600" not in app_list.split("item.active %}")[1].split('"')[0]


def test_unfold_border_radius_matches_hoocon_scale() -> None:
    """Unfold rounded-default uses the same 0.75rem corner scale as Hoocon tokens."""
    assert settings.UNFOLD["BORDER_RADIUS"] == "0.75rem"


def test_unfold_environment_badge_is_tuple_not_string() -> None:
    """ENVIRONMENT badge must be (label, type) so label.html gets full release string."""
    from config.release import release_label, unfold_environment_badge

    badge = settings.UNFOLD["ENVIRONMENT"]
    assert badge == unfold_environment_badge()
    assert isinstance(badge, tuple)
    assert badge[0] == release_label()
    assert len(badge[0]) > 1


def test_unfold_base_colors_are_neutral_gray() -> None:
    """Unfold base scale must not use default blue-tinted oklch backgrounds."""
    base = settings.UNFOLD["COLORS"]["base"]
    assert base["50"] == "#f3f4f7"
    assert base["950"] == "#0f0f10"
    assert all(not str(value).startswith("oklch") for value in base.values())


@pytest.mark.django_db
def test_admin_injects_neutral_base_theme_colors() -> None:
    """Inline Unfold theme colors expose neutral base-50 for body/sidebar canvas."""
    admin_user = User.objects.create_superuser(
        username="admin-base-colors",
        email="admin-base-colors@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "--color-base-50: rgb(243, 244, 247)" in html
    assert "--border-radius: 0.75rem" in html
    assert "oklch(98.5% .002 247" not in html


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
    assert 'data-hoocon-phone-tab="home"' in html
    assert "data-match-exact" in html
    assert 'data-hoocon-phone-tab="leads"' in html
    assert 'data-hoocon-phone-tab="chat"' in html
    assert 'data-hoocon-phone-tab="clients"' in html
    assert "hoocon-phone-home-link" in html
    assert 'href="/admin/"' in html or 'href="/admin"' in html
    assert "data-hoocon-phone-more-open" in html
    assert 'id="hoocon-phone-more"' in html
    assert "hoocon-phone-more__handle" in html
    assert "data-hoocon-phone-more-page-actions" in html
    assert "hoocon-phone-more__page-actions-wrap" in html
    assert "hoocon-phone-tab__icon" in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "viewport-fit=cover" in html

    phone_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-phone.css").read_text(
        encoding="utf-8"
    )
    assert "hoocon-phone-tabs" in phone_css
    assert "hoocon-phone-select-mode" in phone_css
    assert "safe-area-inset-bottom" in phone_css
    assert "hoocon-page-bg" in phone_css
    assert "hoocon-shadow-soft" in phone_css
    assert "hoocon-phone-header-menu" in phone_css
    assert "overflow-x: clip" in phone_css
    assert "body.hoocon-phone-ready.change-form #content-main > form" in phone_css
    assert "--hoocon-phone-header-h:" in phone_css
    assert "body.hoocon-phone-ready.change-form .hoocon-admin-header" in phone_css
    assert (
        "position: fixed !important"
        in phone_css.split("body.hoocon-phone-ready.change-form .hoocon-admin-header")[1].split("}")[0]
    )
    scroll_margin_selector = (
        "body.hoocon-phone-ready.change-form fieldset.module,\n"
        '  body.hoocon-phone-ready.change-form [data-inline-type="tabular"]'
    )
    assert scroll_margin_selector in phone_css
    assert "scroll-margin-top:" in phone_css
    assert "min-width: 0 !important" in phone_css.split("Fieldset defaults to min-width:min-content")[1].split("}")[0]
    assert "body.hoocon-phone-ready.change-form fieldset.module .form-rows" in phone_css
    stacked_inline_block = phone_css.split("Stacked inlines (e.g. Telegram profile)")[1].split(
        "Autocomplete FK: native <select> is clipped/absolutely positioned"
    )[0]
    assert "body.hoocon-phone-ready.change-form .formset-wrapper fieldset.module.border-l" in stacked_inline_block
    stacked_fieldset_rule = stacked_inline_block.split(
        "body.hoocon-phone-ready.change-form .formset-wrapper fieldset.module.border-l"
    )[1].split("}")[0]
    assert "margin-left: 0 !important" in stacked_fieldset_rule
    assert "border-left-width: 0 !important" in stacked_fieldset_rule
    assert "fieldset.module.border-l::before" in stacked_inline_block
    assert (
        "display: none !important" in stacked_inline_block.split("fieldset.module.border-l::before")[1].split("}")[0]
    )
    related_widget_block = phone_css.split("Autocomplete FK: native <select> is clipped/absolutely positioned")[
        1
    ].split("/* Unfold bulk-actions")[0]
    assert ".select2-container" in related_widget_block
    assert "flex: 1 1 0" in related_widget_block
    assert '[x-ref^="relatedWidgetWrapper"]' in related_widget_block
    assert "margin-left: 0" in related_widget_block
    assert "select:not(.select2-hidden-accessible)" in related_widget_block
    assert "#content-main form .related-widget-wrapper:has(.selector)" in related_widget_block
    assert (
        "display: block !important"
        in related_widget_block.split("#content-main form .related-widget-wrapper:has(.selector)")[1].split("}")[0]
    )
    assert (
        "flex-direction: column"
        in related_widget_block.split("#content-main form .related-widget-wrapper .selector")[1].split("}")[0]
    )
    assert (
        "align-items: stretch"
        in related_widget_block.split(".field-line .grow .flex-col.items-center.w-full")[1].split("}")[0]
    )
    assert ".selector-chooser" in related_widget_block
    assert "hoocon-lead-board #changelist" in phone_css
    # Shell itself is the fixed chrome (tabs are relative inside it).
    assert "body.hoocon-phone-ready .hoocon-phone-shell" in phone_css
    shell_rule = phone_css.split("body.hoocon-phone-ready .hoocon-phone-shell")[1].split("}")[0]
    assert "position: fixed" in shell_rule
    assert "bottom: 0" in shell_rule
    assert "--hoocon-phone-viewport-inset" in shell_rule
    assert "padding-inline: var(--hoocon-phone-edge-inset" in shell_rule
    assert "padding-bottom: calc(" in shell_rule
    assert "z-index: 100" in shell_rule
    filter_sheet_rule = phone_css.split(
        "/* Changelist filter sheet — above floating bottom tabs (shell z-index 100). */"
    )[1].split("}")[0]
    assert "z-index: 130 !important" in filter_sheet_rule
    assert "#changelist-filter" in filter_sheet_rule
    tabs_rule = phone_css.split(".hoocon-phone-tabs")[1].split("}")[0]
    assert "position: relative" in tabs_rule
    assert "position: fixed" not in tabs_rule
    assert "width: 100%" in tabs_rule
    assert "max-width: 100%" in tabs_rule
    assert "border-radius: 999px" in tabs_rule
    assert "background: rgba(255, 255, 255, 0.72)" in tabs_rule
    assert "blur(80px)" in tabs_rule
    assert "hoocon-phone-tab__icon" in phone_css
    assert "hoocon-phone-tab--active" in phone_css
    assert "backdrop-filter: blur(20px)" in phone_css
    assert "--hoocon-phone-chrome-h: 5.25rem" in phone_css
    assert "max(1rem, env(safe-area-inset-bottom, 0px))" in phone_css
    assert "background: transparent" in shell_rule
    assert "hoocon-phone-more__handle" in phone_css
    more_sheet_rule = phone_css.split(".hoocon-phone-more__sheet")[1].split("}")[0]
    assert "max-height: 90vh" in more_sheet_rule
    assert "height: auto" in more_sheet_rule
    assert re.search(r"(?<![\w-])height:\s*90vh", more_sheet_rule) is None

    phone_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-shell.js").read_text(
        encoding="utf-8"
    )
    assert "hoocon-phone-ready" in phone_js
    assert "max-width: 767px" in phone_js
    assert "relocateHeaderTools" in phone_js
    assert "relocateActionList" in phone_js
    assert "data-hoocon-phone-page-action-from" in phone_js
    assert 'movePageAction(child, "header-tools", mount)' in phone_js
    assert "data-hoocon-phone-more-page-actions" in phone_js
    assert "hoocon-phone-more__page-actions" in phone_css
    assert "data-hoocon-phone-header-menu" in phone_js
    assert "shell.parentElement !== document.body" in phone_js
    assert "document.body.appendChild(shell)" in phone_js
    assert "isCursorEmbeddedBrowser" in phone_js
    assert "CURSOR_VIEWPORT_INSET" in phone_js
    assert "--hoocon-phone-viewport-inset" in phone_js
    assert "--hoocon-phone-viewport-inset" in phone_css

    badges_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-live-badges.js").read_text(
        encoding="utf-8"
    )
    assert "data-hoocon-phone-leads-badge" in badges_js
    assert "data-hoocon-phone-support-badge" in badges_js


def test_admin_phone_support_messenger_signal_layout() -> None:
    """Phone Чат: Signal-like inbox rows + full-screen thread (loaded phone CSS)."""
    phone_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-phone.css").read_text(
        encoding="utf-8"
    )
    assert "hoocon-support-inbox" in phone_css
    assert "hoocon-support-thread" in phone_css
    assert "grid-template-areas:" in phone_css
    assert '"avatar name time"' in phone_css
    assert '"avatar preview unread"' in phone_css
    assert "border-radius: 50% !important" in phone_css
    assert "body.hoocon-phone-ready.hoocon-support-thread .hoocon-phone-shell" in phone_css
    assert "body.hoocon-phone-ready.hoocon-support-thread .hoocon-messenger__back" in phone_css
    assert (
        "position: fixed"
        in phone_css.split(
            "body.hoocon-phone-ready.hoocon-support-thread .hoocon-messenger",
        )[1].split("}")[0]
    )
    assert "#content-main > form" in phone_css

    messenger_css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-support-messenger.css").read_text(
        encoding="utf-8"
    )
    assert "hoocon-inbox-avatar" in messenger_css
    assert "body.hoocon-support-inbox" in messenger_css
    assert "hoocon-inbox-avatar--web" in messenger_css
    assert "background: var(--hm-brand" in messenger_css
    assert "box-shadow: none" in messenger_css.split(".hoocon-messenger__send {")[1].split("}")[0]
    assert "hoocon-messenger__back" in messenger_css
    assert ".hoocon-messenger__composer textarea::placeholder" in messenger_css
    assert (
        "font-size: 0.8125rem"
        in messenger_css.split(".hoocon-messenger__composer textarea::placeholder")[1].split("}")[0]
    )
    phone_textarea_rule = phone_css.split(
        "body.hoocon-phone-ready.hoocon-support-thread .hoocon-messenger__composer textarea"
    )[1].split("}")[0]
    assert "height: var(--hoocon-phone-tap)" in phone_textarea_rule
    assert "min-height: var(--hoocon-phone-tap)" in phone_textarea_rule
    phone_avatar_rule = phone_css.split("body.hoocon-phone-ready.hoocon-support-thread .hoocon-messenger__avatar")[
        1
    ].split("}")[0]
    assert "width: var(--hoocon-phone-tap)" in phone_avatar_rule
    assert "background: var(--hm-brand" in phone_avatar_rule
    phone_send_rule = phone_css.split(
        "body.hoocon-phone-ready.hoocon-support-thread .hoocon-messenger__send {\n"
        "    min-width: var(--hoocon-phone-tap)"
    )[1].split("}")[0]
    assert "box-shadow: none" in phone_send_rule
    assert "background: var(--hm-brand" in phone_send_rule


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


def test_changelist_actions_bar_offsets_full_sidebar() -> None:
    """Bulk actions bar must not sit under the 260px desktop sidebar (was 72px)."""
    template = (Path(__file__).resolve().parents[1] / "templates/unfold/helpers/change_list_actions.html").read_text(
        encoding="utf-8"
    )
    assert "hoocon-changelist-actions-bar" in template
    assert "nav-sidebar" in template
    assert "? 72 :" not in template


def test_changelist_filter_sheet_has_back_to_close() -> None:
    """Filter sheet below 2xl exposes iOS back control that closes filterOpen."""
    template = (
        Path(__file__).resolve().parents[1] / "templates/unfold/helpers/change_list_filter_vertical.html"
    ).read_text(encoding="utf-8")
    assert "hoocon-changelist-filter-toolbar" in template
    assert "hoocon-changelist-filter-back" in template
    assert 'x-on:click="filterOpen = false"' in template
    assert "2xl:hidden" in template
    assert "Назад" in template

    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    filter_back_block = css.split("/* Changelist filter sheet — iOS back row to close")[1].split(
        "/* OS27 glass search chip"
    )[0]
    assert "@media (max-width: 1535px)" in filter_back_block
    assert ".hoocon-changelist-filter-back" in filter_back_block
    assert "color: var(--os27-accent, var(--hoocon-primary))" in filter_back_block


def test_os27_css_covers_settings_layout() -> None:
    """OS27 layer ships macOS/iOS Settings tokens and grouped surfaces."""
    css = _OS27_CSS.read_text(encoding="utf-8")
    assert "--os27-accent: var(--hoocon-primary" in css
    assert "--os27-sidebar-w: 16.25rem" in css
    assert "--os27-group-radius: var(--hoocon-radius)" in css
    assert "border-radius: var(--hoocon-radius-sm)" in css
    assert "--os27-bg: #f2f2f7" in css
    assert "html.dark" in css
    dark_tokens = css.split(".dark,\nhtml.dark {", 1)[1].split("}", 1)[0]
    assert "--os27-accent: var(--hoocon-primary-on-dark" in dark_tokens
    assert "--os27-accent-hover:" in dark_tokens
    assert "body.hoocon-os27.hoocon-phone-ready.change-form fieldset.module" in css
    assert (
        "overflow: visible"
        in css.split("body.hoocon-os27.hoocon-phone-ready.change-form fieldset.module")[1].split("}")[0]
    )
    assert "body.hoocon-os27 .hoocon-dash__quick" in css
    assert "hoocon-os27-sidebar-panel" in css
    assert "hoocon-glass-search-chip" in css
    assert "blur(80px)" in css
    assert "box-shadow: none !important" in css
    assert "@media (min-width: 1024px)" in css
    assert "@media (min-width: 768px)" in css
    assert "/* ── Sidebar nav (tablet flyout + desktop fixed panel)" in css
    assert "@media (min-width: 768px) and (max-width: 1023px)" in css
    assert "@media (max-width: 767px)" in css
    assert "table.hoocon-admin-table-stacked:not(.hoocon-admin-card-table)" in css
    assert ":has(table.hoocon-admin-card-table)" in css
    assert "hoocon-dash + .hoocon-dash__apps" in css
    sidebar_search_rule = css.split("body.hoocon-os27 .hoocon-sidebar-search {")[1].split(
        "body.hoocon-os27 .hoocon-sidebar-search > div"
    )[0]
    assert "border: 0" in sidebar_search_rule
    assert "background: transparent" in sidebar_search_rule
    os27_search_chip = css.split("body.hoocon-os27 .hoocon-glass-search-chip {")[1].split("}")[0]
    assert "blur(80px)" in os27_search_chip
    assert "--os27-surface-muted" in os27_search_chip
    assert "hoocon-desktop-settings-sidebar" in css
    assert "hoocon-desktop-settings-detail__hero" in css
    assert "hoocon-desktop-settings-app" in css
    assert "hoocon-changelist-actions-bar" in css
    assert "width: 50vw" in css
    assert "left: auto !important" in css
    assert "right: 0 !important" in css
    assert "body.hoocon-os27.change-form #page" in css
    assert "overflow-x: clip" in css
    assert "body.hoocon-os27.change-form .selector" in css
    selector_global = css.split("/* Change form: clip overflow + constrain M2M selector")[1].split(
        "/* ── Sidebar nav (tablet flyout + desktop fixed panel)"
    )[0]
    assert "#content-main form .related-widget-wrapper:has(.selector)" in selector_global
    assert "body.hoocon-os27.change-form .selector select" in selector_global
    assert (
        "max-width: 100%" in selector_global.split("body.hoocon-os27.change-form .selector-available")[1].split("}")[0]
    )
    submit_row_rule = css.split("body.hoocon-os27.change-form #submit-row")[1].split("}")[0]
    assert "position: fixed !important" in submit_row_rule
    assert "left: var(--os27-sidebar-w" in submit_row_rule
    assert "z-index: 110 !important" in submit_row_rule
    submit_container_rule = css.split("body.hoocon-os27.change-form #submit-row .container")[1].split("}")[0]
    assert "margin-inline: 0 !important" in submit_container_rule
    assert "width: 100% !important" in submit_container_rule
    assert (
        "pointer-events: none"
        in css.split('body.hoocon-os27.change-form #submit-row [class*="backdrop-blur"]')[1].split("}")[0]
    )


def test_unfold_extras_css_covers_lead_ui() -> None:
    """Extras CSS keeps lead sticker, status tags, open button, stats layout."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    assert "--hoocon-primary: #dc1313" in css
    assert "--hoocon-primary-hover: #b01010" in css
    assert "--hoocon-primary-on-dark: #f87171" in css
    assert "--hoocon-page-bg: #f3f4f7" in css
    assert "--hoocon-input-glass-bg:" in css
    assert "--hoocon-input-glass-blur:" in css
    assert "--hoocon-phone-edge-inset: 0.5rem" in css
    assert "--hoocon-group-inset: 1rem" in css
    grouped_inset_block = css.split("/*\n * Grouped card inset dividers")[1].split(
        "/* Soft canvas behind Unfold white cards"
    )[0]
    assert "left: var(--hoocon-group-inset)" in grouped_inset_block
    assert "right: var(--hoocon-group-inset)" in grouped_inset_block
    assert ".hoocon-desktop-settings-sidebar__list > li:not(:last-child)::after" in grouped_inset_block
    assert ".hoocon-desktop-settings-sidebar__account::after" in grouped_inset_block
    assert "#changelist #changelist-filter ul.flex-col > li:not(:last-child)::after" in grouped_inset_block
    assert "#changelist #changelist-filter ul.flex:not(.flex-col)" not in grouped_inset_block
    assert "Boolean segments (ul.flex without flex-col) keep Unfold border-r" in grouped_inset_block
    assert "border-bottom: 0 !important" in grouped_inset_block
    assert ".hoocon-grouped-inset-dividers > li" in grouped_inset_block
    assert "body.bg-base-50" in css
    assert "--hoocon-radius: 0.75rem" in css
    fieldset_desc = css.split("fieldset.module > div.leading-relaxed.text-subtle")[1].split("}")[0]
    assert "padding-inline: 0.75rem" in fieldset_desc
    assert "overflow-wrap: anywhere" in fieldset_desc
    input_glass_block = css.split("/* Admin text fields: frosted glass fill")[1].split(
        "/* Change-form submit row — compact labels"
    )[0]
    assert "backdrop-filter: var(--hoocon-input-glass-blur)" in input_glass_block
    assert "background: var(--hoocon-input-glass-bg) !important" in input_glass_block
    assert "background: var(--hoocon-input-glass-bg-focus) !important" in input_glass_block
    assert "#changelist-search input" not in input_glass_block
    filter_layout_block = css.split("/*\n * Unfold vertical changelist filter")[1].split("/* OS27 glass search chip")[
        0
    ]
    assert "position: fixed !important" in filter_layout_block
    assert "#changelist #changelist-filter > div.z-20" in filter_layout_block
    assert "flex: 0 0 20rem" in filter_layout_block
    assert "width: 100% !important" in filter_layout_block.split("@media (max-width: 767px)")[1]
    assert "Filter panel canvas muted" in css
    assert (
        "#changelist #changelist-filter > div.z-20"
        in css.split("Filter panel canvas muted")[1].split("/* OS27 glass search chip")[0]
    )
    assert (
        "background: var(--hoocon-page-bg) !important"
        in css.split("Filter panel canvas muted")[1].split("/* OS27 glass search chip")[0]
    )
    assert (
        "#changelist #changelist-filter ul"
        in css.split("Filter panel canvas muted")[1].split("/* OS27 glass search chip")[0]
    )
    assert (
        "background: var(--hoocon-surface) !important"
        in css.split("Filter panel canvas muted")[1].split("/* OS27 glass search chip")[0]
    )
    search_chip_block = css.split("/* OS27 glass search chip")[1].split("/* Login / OTP")[0]
    assert ".hoocon-glass-search-chip" in search_chip_block
    assert "--hoocon-search-glass-bg" in css
    assert "--hoocon-search-glass-blur" in css
    assert "backdrop-filter: var(--hoocon-search-glass-blur)" in search_chip_block
    assert "blur(80px)" in css.split("--hoocon-search-glass-blur:")[1].split(";")[0]
    assert "#changelist-search #searchbar" in search_chip_block
    assert "background: transparent !important" in search_chip_block
    assert "#changelist-search kbd" in search_chip_block
    assert ".select2-selection--single" in input_glass_block
    assert "@supports not ((backdrop-filter: blur(1px))" in input_glass_block
    submit_row_buttons = css.split("/* Change-form submit row — compact labels")[1].split("/* OS27 glass search chip")[
        0
    ]
    assert "#submit-row .container button" in submit_row_buttons
    assert "font-size: 0.8125rem !important" in submit_row_buttons
    assert '[data-inline-type="tabular"] .tabular.inline-related' in css
    assert 'body.change-form [data-inline-type="tabular"] table.formset tbody.form-group' in css
    assert "tr.form-row:has(.delete:checked)" in css
    assert "tbody.form-group > tr.hidden" in css
    assert "--hoocon-radius-sm:" in css
    assert "--hoocon-radius-lg:" in css
    assert "--border-radius: var(--hoocon-radius)" in css
    assert ".rounded-default" in css
    assert "--hoocon-card-pad:" in css
    assert "--hoocon-kpi-strip-h:" in css
    assert ".hoocon-lead-stats__card::after" in css
    assert "nth-child(4n + 1)::after" not in css
    assert ".hoocon-integrations__card--on::after" in css
    assert "background: #16a34a" in css
    assert ".dark .hoocon-dash__panel-head a" in css
    assert ".hoocon-admin-lead-sticker" in css
    assert "hoocon-admin-lead-sticker__count" in css
    assert ".hoocon-admin-support-sticker--active" in css
    assert ".hoocon-lead-status--new" in css
    assert "a.hoocon-admin-lead-open" in css
    assert ".hoocon-lead-stats" in css
    assert ".hoocon-admin-breadcrumbs" in css
    assert "--os27-sidebar-w" in css or "16.25rem" in css
    assert ".hoocon-sidebar-label" in css
    assert ".hoocon-nav-shell" in css
    tablet_nav_block = css.split("@media (max-width: 1023px)")[1].split("@media (min-width: 1024px)")[0]
    assert ".hoocon-nav-backdrop" in tablet_nav_block
    assert "body.hoocon-nav-overlay-open" in tablet_nav_block
    assert "hoocon-desktop-settings-nav" in tablet_nav_block
    assert (
        "display: none !important"
        in tablet_nav_block.split("hoocon-desktop-settings-nav")[1].split(".hoocon-nav-panel")[0]
    )
    assert "transform: translateX(-100%)" in tablet_nav_block
    assert "transform: translateX(0)" in tablet_nav_block
    assert "var(--os27-sidebar-w, 16.25rem)" in tablet_nav_block
    assert "transition:" in tablet_nav_block
    assert ".hoocon-admin-header" in css
    header_actions_rule = css.split(".hoocon-header-userlinks > div > ul.bg-white")[1].split("}")[0]
    assert "border-radius: var(--hoocon-radius" in header_actions_rule
    assert "overflow: hidden" in header_actions_rule
    assert ".hoocon-all-apps-panel" in css
    assert ".hoocon-all-apps-flyout" in css
    assert "z-index: 80" in css
    assert "min(28rem" in css
    assert ".hoocon-integrations" in css
    assert ".hoocon-integrations__actions" in css
    assert "hoocon-admin-table-stacked" in css
    assert "hoocon-admin-cell-blank" in css
    assert "hoocon-admin-card-table" in css
    assert "Changelist card grid canvas" in css
    assert "#changelist table.hoocon-admin-card-table.hoocon-admin-table-stacked" in css
    assert "background-color: var(--hoocon-page-bg) !important" in css
    assert "table.hoocon-lead-stats__table.hoocon-admin-table-stacked" in css
    assert "body.hoocon-lead-board" in css
    assert "body.hoocon-lead-board #content.container" in css
    assert "max-width: none !important" in css
    assert "@media (min-width: 640px)" in css
    assert "repeat(2, minmax(0, 1fr))" in css
    assert "padding-left: 0.5rem !important" in css
    assert "justify-content: stretch" in css
    assert "display: contents" in css
    assert "gap: 1.15rem 1.25rem" in css
    assert "align-items: stretch" in css
    assert "margin-top: auto" in css
    assert ".hoocon-lead-kanban" in css
    assert ".hoocon-lead-view-toggle" in css
    assert "hoocon-lead-wall-heading" in css
    assert "box-shadow: var(--hoocon-shadow-soft)" in css
    assert "/* Card hierarchy — title / meta / badges" in css
    assert "td.field-email_id" in css
    assert "td.field-sku_code" in css
    assert "td.field-answer" in css
    assert "min-height: 5.5rem" in css
    assert "order: -2" in css
    assert "font-weight: 700" in css
    assert "body:not(.hoocon-support-inbox) #changelist" in css
    assert "height: auto !important" in css
    assert "display: grid !important" in css
    assert 'td[class*="field-is_"]' in css

    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-tables.js").read_text(encoding="utf-8")
    assert "table.hoocon-lead-stats__table" in js
    assert "isUnfoldTabularInline" in js
    assert "[data-inline-type='tabular'] table.formset" not in js.split("CARD_TABLE_SELECTORS")[1].split("];")[0]
    assert 'table.closest("#changelist")' in js
    assert "hoocon-lead-kanban__cards" in js
    assert "hoocon-phone-filter-chips" in js

    board_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-leads-board.js").read_text(
        encoding="utf-8"
    )
    assert "hoocon-lead-wall-heading" in board_js
    assert "hoocon-lead-kanban" in board_js
    assert 'view === "kanban"' in board_js
    assert "restoreRowsToTable(table)" in board_js
    assert "Re-entrant" in board_js


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
def test_admin_sidebar_os27_full_width_settings_layout() -> None:
    """Desktop sidebar uses macOS 27 Settings full-width panel (not icon rail)."""
    admin_user = User.objects.create_superuser(
        username="admin-os27-sidebar",
        email="admin-os27-sidebar@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()
    assert "hoocon-os27-sidebar" in html
    assert "hoocon-os27-sidebar-panel" in html
    assert "hoocon-nav-shell" in html
    assert "hoocon-nav-backdrop" in html
    assert "hoocon-nav-overlay-open" in html
    assert "hoocon-nav-panel" in html
    assert "sidebarWidth: 260" in html
    assert "panelWidth" in html
    assert "isDesktopNav" in html
    assert "sidebarPeek" not in html
    assert "railWidth" not in html
    assert "hoocon-sidebar-shortcut" in html
    assert "Закрыть меню" in html
    assert "data-hoocon-desktop-settings-sidebar" in html
    assert "data-hoocon-desktop-settings-select" in html
    assert "hoocon-admin-desktop-settings.js" in html
    assert "data-hoocon-desktop-settings-detail" in html


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
    assert "hoocon-admin-webpush.js" in html
    assert "hoocon-admin-tables.js" in html
    assert "hoocon-admin-phone-shell.js" in html
    assert "hoocon-admin-phone-settings.js" in html
    assert "hoocon-os27.css" in html
    assert "hoocon-admin-phone.css" in html
    assert 'name="theme-color" content="#5a626c"' in html

    webpush_js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-webpush.js").read_text(
        encoding="utf-8"
    )
    assert "clear_support: true" in webpush_js
    assert "await sub.unsubscribe()" in webpush_js

    sw = client.get("/admin/sw.js")
    assert sw.status_code == 200
    assert sw["Service-Worker-Allowed"] == "/admin/"

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
