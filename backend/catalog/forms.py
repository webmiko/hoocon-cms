"""Admin form for uploading a 1C stock Excel file."""

from __future__ import annotations

from django import forms

from catalog.validators import validate_stock_xlsx_upload


class StockUploadForm(forms.Form):
    """Single-file upload for warehouse stock (.xlsx)."""

    file = forms.FileField(
        label="Файл остатков (.xlsx)",
        help_text="Колонки: «Артикул» и «Свободно» (или «Остатки» / «Остаток»).",
        allow_empty_file=False,
    )

    def clean_file(self) -> object:
        """Validate extension, size, and ZIP magic bytes."""
        uploaded = self.cleaned_data["file"]
        validate_stock_xlsx_upload(uploaded)
        return uploaded
