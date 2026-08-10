"""Admin form for uploading a 1C stock Excel file."""

from __future__ import annotations

from django import forms
from unfold.widgets import UnfoldAdminFileFieldWidget

from catalog.validators import validate_stock_xlsx_upload


class StockFileWidget(UnfoldAdminFileFieldWidget):
    """Unfold file picker with RU placeholder for stock XLSX."""

    template_name = "admin/catalog/widgets/stock_file_input.html"


class StockUploadForm(forms.Form):
    """Single-file upload for warehouse stock (.xlsx)."""

    file = forms.FileField(
        label="Файл остатков (.xlsx)",
        help_text="Колонки: «Артикул» и «Свободно» (или «Остатки» / «Остаток»).",
        allow_empty_file=False,
        widget=StockFileWidget,
    )

    def clean_file(self) -> object:
        """Validate extension, size, and ZIP magic bytes."""
        uploaded = self.cleaned_data["file"]
        validate_stock_xlsx_upload(uploaded)
        return uploaded
