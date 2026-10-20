"""Shared assertions for the CRM and lead mail compose pages."""

from __future__ import annotations


def assert_send_now_is_one_label(html: str) -> None:
    """Footer has the switch captions once; a second label would toggle the click back.

    The caption flips with the state, so the field name lives in ``aria-label``.
    """
    footer = html.split('class="hoocon-mail-compose__footer"', 1)[1]
    footer = footer.split('class="hoocon-mail-compose__actions"', 1)[0]
    assert footer.count("<label") == 1
    assert "hoocon-bool-toggle" in footer
    assert 'hoocon-bool-toggle__state--off">Черновик</span>' in footer
    assert 'hoocon-bool-toggle__state--on">Отправить сразу</span>' in footer
    assert footer.count(">Отправить сразу<") == 1
    assert 'aria-label="Отправить сразу"' in footer
