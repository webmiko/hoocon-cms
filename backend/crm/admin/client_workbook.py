"""Excel import and export views for the client changelist."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from crm.client_import import (
    ClientImportError,
    build_client_template_xlsx,
    export_clients_xlsx,
    import_clients_xlsx,
)
from crm.forms import ClientCardsUploadForm


class ClientWorkbookMixin:
    """Upload and download the client workbook from the client admin."""

    def export_clients_view(self: Any, request: HttpRequest) -> HttpResponse:
        """Download the cards this user can see, in the import column layout."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        payload = export_clients_xlsx(self.get_queryset(request))
        filename = f"klienty-{timezone.localdate().isoformat()}.xlsx"
        response = HttpResponse(
            payload,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def import_clients_template_view(self: Any, request: HttpRequest) -> HttpResponse:
        """Download the client-card workbook (data sheet + ignored example)."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        response = HttpResponse(
            build_client_template_xlsx(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="klienty-shablon.xlsx"'
        return response

    def import_clients_view(self: Any, request: HttpRequest) -> HttpResponse:
        """Upload .xlsx and create client cards plus company requisites."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        changelist_url = reverse("admin:crm_client_changelist")
        template_url = reverse("admin:crm_client_import_clients_template")
        if request.method == "POST":
            form = ClientCardsUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded = form.cleaned_data["file"]
                try:
                    report = import_clients_xlsx(uploaded)
                except ClientImportError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                else:
                    level = messages.SUCCESS if report.created else messages.WARNING
                    self.message_user(request, report.summary(), level)
                    return HttpResponseRedirect(changelist_url)
        else:
            form = ClientCardsUploadForm()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "Загрузить карточки клиентов",
            "form": form,
            "template_url": template_url,
            "changelist_url": changelist_url,
            "media": self.media,
        }
        return render(request, "admin/crm/client/import_clients.html", context)
