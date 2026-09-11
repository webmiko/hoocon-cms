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

    Must live in hoocon-unfold-extras.css — Unfold does not load hoocon-admin.css.
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
    action_list_rule = phone.split(
        "body.hoocon-phone-ready .hoocon-header-userlinks > div > ul.bg-white.max-lg\\:flex"
    )[1].split("body.hoocon-phone-ready .hoocon-phone-header-menu__list")[0]
    assert "position: fixed" in action_list_rule
    assert "z-index: 136" in action_list_rule
    action_header_rule = phone.split(
        "body.hoocon-phone-ready\n    .hoocon-admin-header:has(.hoocon-header-userlinks > div > ul.max-lg\\:flex)"
    )[1].split("body.hoocon-phone-ready .hoocon-admin-header:has(.hoocon-phone-header-menu.is-open) .container")[0]
    assert "z-index: 135" in action_header_rule
    assert "hoocon-lead-board #changelist" in phone
    assert "margin-left: 0 !important" in phone
    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-shell.js").read_text(
        encoding="utf-8"
    )
    assert "relocateHeaderTools" in js
    assert "data-hoocon-phone-header-menu" in js
    assert "isDesktopOnlyTool" in js
    assert "hoocon-lead-view-tool" in js
    board_js = _BOARD_JS.read_text(encoding="utf-8")
    assert 'view === "kanban" && !phone' in board_js


def test_lead_board_css_wall_three_centered_equal_height_cards() -> None:
    """Wall grid: 2 cols from 640px; lift Unfold #content.container cap; 2rem gutters."""
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
    assert "padding-left: 2rem !important" in css
    assert "padding-right: 2rem !important" in css
    # Wall table keeps extra horizontal inset on lead board (768+).
    assert "padding-left: 1.5rem" in css
    open_pin = css[css.index("Pin «Открыть»") : css.index("hoocon-lead-wall-heading")]
    assert "field-open_link" in open_pin
    assert "margin-top: auto" in open_pin


def test_lead_board_css_kanban_head_vertically_centered() -> None:
    """Kanban column title + count share one vertical center line."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    head = _css_rule_body(css, ".hoocon-lead-kanban__head")
    assert "align-items: center" in head
    assert "align-items: baseline" not in head


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
