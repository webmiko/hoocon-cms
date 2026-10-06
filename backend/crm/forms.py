"""Forms for CRM Admin (compose outbound email)."""

from __future__ import annotations

from typing import Any

from django import forms


class ComposeEmailForm(forms.Form):
    """Staff form: write and optionally queue an email to a Client."""

    to_email = forms.EmailField(
        label="Кому",
        max_length=254,
        help_text="Адрес получателя (по умолчанию — email клиента).",
    )
    subject = forms.CharField(label="Тема", max_length=300)
    body = forms.CharField(
        label="Текст письма",
        max_length=20000,
        widget=forms.Textarea(attrs={"rows": 12, "cols": 80}),
        help_text="Не более 20 000 символов.",
    )
    send_now = forms.BooleanField(
        label="Отправить сразу",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "hoocon-toggle"}),
        help_text="Если выключить — сохранится черновик без отправки.",
    )


class SpecImportForm(forms.Form):
    """Staff form: upload an .xlsx spec → draft lead with positions (ЛК-9)."""

    file = forms.FileField(
        label="Файл спецификации (.xlsx)",
        help_text=(
            "Первая страница: колонки «артикул» и «количество». Чужие артикулы "
            "подбираются по карте аналогов; неопознанные попадут в заявку как есть."
        ),
    )

    def clean_file(self) -> Any:
        """Accept only .xlsx up to 5 MB."""
        f = self.cleaned_data["file"]
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Файл больше 5 МБ.")
        if not (f.name or "").lower().endswith(".xlsx"):
            raise forms.ValidationError("Поддерживается только .xlsx.")
        return f
