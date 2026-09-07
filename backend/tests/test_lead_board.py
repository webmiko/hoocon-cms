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


def test_lead_board_css_wall_three_centered_equal_height_cards() -> None:
    """Wall grid: 2 cols, then 3 from 1280px; centered; «Открыть» at footer."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    assert "repeat(2, minmax(0, 24rem))" in css
    assert "repeat(3, minmax(0, 24rem))" in css
    assert "@media (min-width: 1280px)" in css
    assert "justify-content: center" in css
    assert "align-items: stretch" in css
    assert "display: contents" in css
    assert "margin-top: auto" in css
    assert "gap: 1.15rem 1.25rem" in css
    # Inset from Unfold -mx-4 / white results frame.
    assert "margin-left: 0 !important" in css
    assert "padding-left: 1.25rem" in css
    assert "padding-right: 1.25rem" in css
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


@pytest.mark.django_db
def test_lead_changelist_renders_status_badges_for_board_js() -> None:
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
