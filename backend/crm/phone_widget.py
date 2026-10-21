"""Company phone field: one number per row, with a button to add another."""

from __future__ import annotations

from typing import Any

from django import forms
from unfold.widgets import INPUT_CLASSES

from crm.phones import join_phone_numbers, split_phone_numbers
from crm.telephony import normalize_phone_digits


class MultiPhoneWidget(forms.Widget):
    """Repeatable phone inputs. The model still stores them in one column."""

    template_name = "admin/crm/widgets/multi_phone.html"

    class Media:
        js = ("admin/js/hoocon-company-phones.js",)

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        css = " ".join([*INPUT_CLASSES, (attrs or {}).get("class", "")]).strip()
        super().__init__(attrs={**(attrs or {}), "class": css, "maxlength": "50"})

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        numbers = split_phone_numbers("" if value is None else str(value)) or [""]
        rows: list[dict[str, str | bool]] = []
        for index, number in enumerate(numbers):
            digits = normalize_phone_digits(number)
            rows.append(
                {
                    "number": number,
                    "tel": f"+{digits}" if 10 <= len(digits) <= 15 else "",
                    "is_first": index == 0,
                },
            )
        context["rows"] = rows
        return context

    def value_from_datadict(self, data: Any, files: Any, name: str) -> str:
        del files
        if hasattr(data, "getlist"):
            parts = data.getlist(name)
        else:
            raw = data.get(name)
            parts = [raw] if raw else []
        return join_phone_numbers(*(part or "" for part in parts))
