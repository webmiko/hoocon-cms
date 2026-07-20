"""Forms for CRM Admin (compose outbound email)."""

from __future__ import annotations

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
        help_text="Если снять галочку — сохранится черновик без отправки.",
    )
