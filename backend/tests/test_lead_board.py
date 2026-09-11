"""Regression tests for Admin leads wall / kanban board layout and JS."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from leads.models import Lead

User = get_user_model()

_BACKEND = Path(__file__).resolve().parents[1]
_EXTRAS_CSS = _BACKEND / "static/admin/css/hoocon-unfold-extras.css"
_BOARD_JS = _BACKEND / "static/admin/js/hoocon-admin-leads-board.js"


def _apply_kanban_fn_source(src: str) -> str:
    """Slice ``applyKanban`` body (until ``restoreRowsToTable`` definition)."""
    start = src.index("function applyKanban")
    end = src.index("function restoreRowsToTable", start)
    return src[start:end]


def _css_rule_body(css: str, selector: str) -> str:
    """Return the first ``{...}`` body after ``selector`` (brace-balanced)."""
    start = css.index(selector)
    open_at = css.index("{", start)
    depth = 0
    for i, ch in enumerate(css[open_at:], start=open_at):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[open_at + 1 : i]
    raise AssertionError(f"Unclosed CSS rule for {selector!r}")


def test_lead_board_css_header_object_tools_row() -> None:
    """Sticky header object-tools stay a horizontal row (bare <li>, no ul).

    Must live in hoocon-unfold-extras.css (UNFOLD STYLES entry).
    """
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    row = _css_rule_body(css, ".hoocon-header-object-tools")
    assert "display: flex" in row
    assert "flex-direction: row" in row
    assert "align-items: center" in row
    items = _css_rule_body(css, ".hoocon-header-object-tools > li")
    assert "display: inline-flex" in items
    assert "list-style: none" in items
    userlinks = _css_rule_body(css, ".hoocon-header-userlinks")
    assert "margin-right: 2rem" in userlinks


def test_lead_board_css_phone_header_hamburger() -> None:
    """Phone CSS/JS move overflow header tools into a hamburger; Add stays out."""
    phone = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-admin-phone.css").read_text(
        encoding="utf-8"
    )
    assert "hoocon-phone-header-menu" in phone
    assert "hoocon-phone-header-menu__btn" in phone
    assert "hoocon-lead-view-tool" in phone
    assert "display: none !important" in phone
    assert ":has(.hoocon-phone-header-menu.is-open)" in phone
    assert "overflow: visible" in phone
    open_header_rule = phone.split(
        "body.hoocon-phone-ready .hoocon-admin-header:has(.hoocon-phone-header-menu.is-open)"
    )[1].split("body.hoocon-phone-ready .hoocon-header-userlinks")[0]
    assert "z-index: 135" in open_header_rule
    open_panel_rule = phone.split(
        "body.hoocon-phone-ready .hoocon-phone-header-menu.is-open .hoocon-phone-header-menu__panel"
    )[1].split("body.hoocon-phone-ready .hoocon-phone-header-menu__list")[0]
    assert "position: fixed" in open_panel_rule
    assert "z-index: 136" in open_panel_rule
    assert "body.hoocon-phone-ready [data-hoocon-phone-action-list]" in phone
    action_list_hide = phone.split("body.hoocon-phone-ready [data-hoocon-phone-action-list]")[1].split("}")[0]
    assert "display: none !important" in action_list_hide
    assert "hoocon-phone-more__page-actions" in phone
    assert "hoocon-lead-board #changelist" in phone
    assert "margin-left: 0 !important" in phone
    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-shell.js").read_text(
        encoding="utf-8"
    )
    assert "relocateHeaderTools" in js
    assert "relocateActionList" in js
    assert "data-hoocon-phone-page-action-from" in js
    assert 'movePageAction(child, "header-tools", mount)' in js
    assert "data-hoocon-phone-more-page-actions" in js
    assert "data-hoocon-phone-header-menu" in js
    assert "isDesktopOnlyTool" in js
    assert "hoocon-lead-view-tool" in js
    board_js = _BOARD_JS.read_text(encoding="utf-8")
    assert 'view === "kanban" && !phone' in board_js


def test_lead_board_css_wall_three_centered_equal_height_cards() -> None:
    """Wall grid: 2 cols from 640px; lift Unfold #content.container cap; 0.5rem gutters."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    assert "@media (min-width: 640px)" in css
    assert "repeat(2, minmax(0, 1fr))" in css
    wall_grid = css.split("@media (min-width: 640px)")[1].split("/* Leads board:")[0]
    assert "display: grid !important" in wall_grid
    assert "repeat(3, minmax(0, 1fr))" not in wall_grid
    assert "justify-content: stretch" in css
    assert "align-items: stretch" in css
    assert "display: contents" in css
    assert "margin-top: auto" in css
    assert "gap: 1.15rem 1.25rem" in css
    assert "margin-left: 0 !important" in css
    # Unfold container mx-auto was capping the board at 768px.
    assert "body.hoocon-lead-board #content.container" in css
    assert "max-width: none !important" in css
    board_block = css.split("/* Leads board: lift Unfold container cap")[1].split(
        "/* Leads kanban (tablet/desktop only). */"
    )[0]
    assert "padding-left: 0.5rem !important" in board_block
    assert "padding-right: 0.5rem !important" in board_block
    # Wall cards — 0.5rem inset inside the bordered board canvas.
    assert "padding: 0.5rem" in board_block
    assert "hoocon-lead-kanban-source" in board_block
    # Search bar + table span #content inner width (no Unfold lg:p-3 / #main.grow inset).
    assert "body.hoocon-lead-board #main > div.grow" in board_block
    search_bar = _css_rule_body(css, "body.hoocon-lead-board #changelist .grow.min-w-0 > .flex.lg\\:border")
    assert "padding-left: 0.5rem !important" in search_bar
    assert "padding-right: 0.5rem !important" in search_bar
    assert "align-items: center" in search_bar
    assert "#changelist #changelist-filter .hoocon-lead-sort-filter" in css
    assert "body.hoocon-lead-board #changelist #result_list" in board_block
    # Lift os27 #content-main max-width (~50rem) so board fills the main column.
    content_main = _css_rule_body(css, "body.hoocon-lead-board #content-main")
    assert "max-width: none !important" in content_main
    assert "margin-left: 0 !important" in content_main
    open_pin = css[css.index("Pin «Открыть»") : css.index("hoocon-lead-wall-heading")]
    assert "field-open_link" in open_pin
    assert "margin-top: auto" in open_pin


def test_lead_board_css_kanban_head_vertically_centered() -> None:
    """Kanban column title + count share one vertical center line."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    head = _css_rule_body(css, ".hoocon-lead-kanban__head")
    assert "align-items: center" in head
    assert "align-items: baseline" not in head


def test_lead_board_css_kanban_board_canvas_matches_wall() -> None:
    """Kanban board canvas uses the same --hoocon-page-bg as wall #result_list."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    overflow = _css_rule_body(css, "#changelist #changelist-form > .overflow-x-auto")
    assert "background-color: var(--hoocon-page-bg) !important" in overflow
    kanban = _css_rule_body(css, 'body.hoocon-lead-board[data-hoocon-lead-view="kanban"] .hoocon-lead-kanban')
    assert "background-color: var(--hoocon-page-bg)" in kanban


def test_lead_board_css_kanban_tight_gutters() -> None:
    """Kanban board + columns use 0.5rem inset (aligned with wall search/cards)."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    marker = "/* Kanban board + columns: 0.5rem inset"
    kanban_block = css.split(marker)[1].split("@media (max-width: 767px)")[0]
    kanban_outer = _css_rule_body(css, 'body.hoocon-lead-board[data-hoocon-lead-view="kanban"] .hoocon-lead-kanban')
    assert "padding: 0.5rem" in kanban_outer
    assert ".hoocon-lead-kanban__col" in kanban_block
    col = _css_rule_body(css, 'body.hoocon-lead-board[data-hoocon-lead-view="kanban"] .hoocon-lead-kanban__col')
    assert "padding: 0.5rem" in col


def test_lead_board_js_kanban_restores_rows_before_rebuild() -> None:
    """Regression: delayed/resize refresh must not discard cards already in kanban.

    Old bug: ``applyKanban`` removed the board (and its rows) then re-read an
    empty table → all columns showed 0.
    """
    src = _BOARD_JS.read_text(encoding="utf-8")
    apply_fn = _apply_kanban_fn_source(src)
    assert "restoreRowsToTable(table)" in apply_fn
    assert apply_fn.index("restoreRowsToTable(table)") < apply_fn.index(
        'className = "hoocon-lead-kanban"',
    )
    # Must not tear down the live board before restoring rows.
    assert "existing.remove()" not in apply_fn
    assert "removeKanban" not in apply_fn
    # Delayed re-entry that previously triggered the bug.
    assert "setTimeout(scheduleRefresh, 50)" in src
    assert "setTimeout(scheduleRefresh, 400)" in src
    assert 'addEventListener("resize", scheduleRefresh)' in src


def test_lead_board_js_classifies_status_badges_and_wall_headings() -> None:
    """Board JS keys off status badge classes and builds wall section titles."""
    src = _BOARD_JS.read_text(encoding="utf-8")
    assert "hoocon-lead-status--new" in src
    assert "hoocon-lead-status--in_progress" in src
    assert "hoocon-lead-status--done" in src
    assert "hoocon-lead-wall-heading" in src
    assert 'STATUS_ORDER = ["new", "in_progress", "done"]' in src
    assert 'new: "Новая"' in src
    assert 'in_progress: "В работе"' in src
    assert 'done: "Завершена"' in src


def test_lead_board_js_kanban_dnd_posts_status_with_csrf() -> None:
    """Kanban DnD posts set-status, updates badge classes, and uses CSRF cookie."""
    src = _BOARD_JS.read_text(encoding="utf-8")
    assert "enableKanbanDragDrop" in src
    assert "enableKanbanDragDrop(board)" in _apply_kanban_fn_source(src)
    assert 'setAttribute("draggable", "true")' in src
    assert "/set-status/" in src
    assert "X-CSRFToken" in src
    assert 'getCookie("csrftoken")' in src
    assert "setRowStatusBadge" in src
    assert "hoocon-lead-status--" in src
    assert "data-hoocon-just-dragged" in src
    tables = (_BACKEND / "static/admin/js/hoocon-admin-tables.js").read_text(encoding="utf-8")
    assert "data-hoocon-just-dragged" in tables


def test_lead_board_css_kanban_status_badge_shrink_wrap() -> None:
    """Kanban status badge cell must not stretch the pill wider than its text."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    badge_block = css.split(".hoocon-lead-kanban__cards > tr > td.field-status_badge::before")[1].split(
        "body.hoocon-lead-board[data-hoocon-lead-view"
    )[0]
    assert "display: flex !important" in badge_block
    assert "width: auto !important" in badge_block
    assert "grid-template-columns: unset" in badge_block
    assert "flex: 0 0 auto" in badge_block


def test_lead_board_css_kanban_dnd_affordances() -> None:
    """Kanban cards use grab cursor; drop target column is highlighted."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    cards = _css_rule_body(css, ".hoocon-lead-kanban__cards > tr")
    assert "cursor: grab" in cards
    assert "hoocon-lead-kanban__dragging" in css
    assert "hoocon-lead-kanban__drop-target" in css


@pytest.mark.django_db
def test_lead_changelist_renders_header_hamburger_markup() -> None:
    """Leads changelist ships phone header hamburger shell in userlinks."""
    Lead.objects.create(
        name="Menu Lead",
        email="menu-lead@example.com",
        message="Проверка гамбургера.",
        status=Lead.LeadStatus.NEW,
    )
    admin_user = User.objects.create_superuser(
        username="lead-header-menu",
        email="lead-header-menu@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/leads/lead/?view=wall").content.decode()
    assert "data-hoocon-phone-header-menu" in html
    assert "data-hoocon-header-object-tools" in html
    assert "data-hoocon-phone-more-page-actions" in html
    assert "hoocon-leads-stats-link" in html
    assert "Меню действий" in html

    """Changelist HTML exposes badge classes so wall/kanban JS can bucket rows."""
    Lead.objects.create(
        name="Board New",
        email="board-new@example.com",
        message="Новая для доски.",
        status=Lead.LeadStatus.NEW,
    )
    Lead.objects.create(
        name="Board Progress",
        email="board-prog@example.com",
        message="В работе для доски.",
        status=Lead.LeadStatus.IN_PROGRESS,
    )
    Lead.objects.create(
        name="Board Done",
        email="board-done@example.com",
        message="Завершена для доски.",
        status=Lead.LeadStatus.DONE,
    )
    admin_user = User.objects.create_superuser(
        username="lead-board-badges",
        email="lead-board-badges@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/leads/lead/?view=wall").content.decode()
    assert "hoocon-lead-status--new" in html
    assert "hoocon-lead-status--in_progress" in html
    assert "hoocon-lead-status--done" in html
    assert "hoocon-admin-leads-board.js" in html
    assert "hoocon-lead-board" in html
    assert 'data-hoocon-lead-view="wall"' in html


@pytest.mark.django_db
def test_lead_changelist_sort_controls_and_name_order() -> None:
    """Changelist exposes А→Я / Я→А sort; ``?o=`` orders rows on the server."""
    Lead.objects.create(
        name="Zulu",
        email="zulu-sort@example.com",
        message="Z",
        status=Lead.LeadStatus.NEW,
    )
    Lead.objects.create(
        name="Alpha",
        email="alpha-sort@example.com",
        message="A",
        status=Lead.LeadStatus.NEW,
    )
    admin_user = User.objects.create_superuser(
        username="lead-board-sort",
        email="lead-board-sort@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)

    html = client.get("/admin/leads/lead/?o=2&view=wall").content.decode()
    assert "hoocon-lead-sort-filter" in html
    assert "Имя · А→Я" in html
    assert "hoocon-lead-sort__select" not in html
    assert "Имя · Я→А" in html
    assert "Компания · А→Я" in html
    assert html.index("Alpha") < html.index("Zulu")

    desc = client.get("/admin/leads/lead/?o=-2&view=wall").content.decode()
    assert desc.index("Zulu") < desc.index("Alpha")


@pytest.mark.django_db
def test_lead_admin_get_queryset_defers_ordering_to_changelist() -> None:
    """LeadAdmin.get_queryset must not hardcode order_by (breaks ``?o=`` sort)."""
    from django.contrib.admin.sites import site
    from django.test import RequestFactory
    from django.urls import resolve

    admin_user = User.objects.create_superuser(
        username="lead-sort-ordering",
        email="lead-sort-ordering@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/leads/lead/")
    request.user = admin_user
    request.resolver_match = resolve("/admin/leads/lead/")
    ma = site._registry[Lead]
    qs = ma.get_queryset(request)
    assert qs.query.order_by == ()


@pytest.mark.django_db
def test_lead_changelist_view_persists_in_session() -> None:
    """``?view=`` is remembered so filters/pagination keep wall or kanban."""
    Lead.objects.create(
        name="Session Lead",
        email="session-lead@example.com",
        message="Проверка сессии вида.",
        status=Lead.LeadStatus.NEW,
    )
    admin_user = User.objects.create_superuser(
        username="lead-board-session",
        email="lead-board-session@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)

    kanban = client.get("/admin/leads/lead/?view=kanban")
    assert kanban.status_code == 200
    assert client.session.get("hoocon_lead_view") == "kanban"
    kanban_html = kanban.content.decode()
    assert 'data-hoocon-lead-view="kanban"' in kanban_html
    assert "document.documentElement.dataset.hooconLeadView" in kanban_html
    assert "?e=1" not in kanban_html
    assert kanban.wsgi_request.GET.get("view") is None  # stripped before ChangeList

    # No view= in URL — session still drives kanban.
    again = client.get("/admin/leads/lead/")
    assert again.status_code == 200
    assert 'data-hoocon-lead-view="kanban"' in again.content.decode()

    wall = client.get("/admin/leads/lead/?view=wall")
    assert wall.status_code == 200
    assert client.session.get("hoocon_lead_view") == "wall"
    assert 'data-hoocon-lead-view="wall"' in wall.content.decode()
