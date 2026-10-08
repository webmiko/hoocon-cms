"""Пустое состояние списка админки: пояснение раздела."""

from __future__ import annotations

from django import template

from config.empty_state import empty_state_help_for

register = template.Library()


@register.simple_tag
def empty_state_help(model_admin: object) -> str:
    """Вернуть пояснение пустого списка для этой админки."""
    return empty_state_help_for(model_admin)
