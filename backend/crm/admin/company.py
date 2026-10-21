"""Company admin with member inline."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin
from config.admin_toggle import LabeledToggleMixin
from crm.admin.filters import WorkQueueFilter
from crm.models import Client, Company, CompanyMember
from crm.phone_widget import MultiPhoneWidget


class CompanyMemberInline(LabeledToggleMixin, TabularInline):
    """Members of a company card (CRM-x)."""

    model = CompanyMember
    extra = 1
    toggle_labels = {"is_confirmed": ("Не подтверждён", "Подтверждён")}
    fields = ("client", "account", "role", "is_confirmed")
    autocomplete_fields = ("client",)


class CompanyAdminForm(forms.ModelForm):
    """Phone is one input per number. The column still stores them together."""

    class Meta:
        model = Company
        fields = "__all__"
        widgets = {"phone": MultiPhoneWidget()}


@admin.register(Company)
class CompanyAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Карточка юрлица: реквизиты + члены (целевая схема CRM-x)."""

    form = CompanyAdminForm

    list_display = ("name", "inn", "city", "relevance", "work_label_list", "next_contact_at", "assignee")
    list_display_links = ("name",)
    list_filter = ("relevance", "region", "niche", WorkQueueFilter, "assignee", "work_labels")
    search_fields = ("name", "inn", "city", "phone", "email", "website", "contact_name")
    autocomplete_fields = ("assignee",)
    filter_horizontal = ("work_labels",)
    readonly_fields = ("company_key", "created_at", "updated_at")
    inlines = (CompanyMemberInline,)
    actions = ("merge_companies_action", "assign_to_me")
    fieldsets = (
        (None, {"fields": ("name", "inn", "legal_address", "city", "region")}),
        (
            "Контакт",
            {"fields": ("contact_name", "phone", "email", "website")},
        ),
        (
            "Работа",
            {"fields": ("niche", "relevance", "assignee", "next_contact_at", "work_labels", "comment")},
        ),
        ("Служебное", {"fields": ("company_key", "created_at", "updated_at")}),
    )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Link to client Excel import and export, following client-card permissions."""
        extra = dict(extra_context or {})
        client_admin = self.admin_site._registry[Client]
        if client_admin.has_add_permission(request):
            extra["client_import_url"] = reverse("admin:crm_client_import_clients")
        if client_admin.has_view_permission(request):
            extra["client_export_url"] = reverse("admin:crm_client_export_clients")
        return super().changelist_view(request, extra_context=extra)

    def has_merge_permission(self, request: HttpRequest) -> bool:
        """Merge deletes the source companies."""
        return self.has_change_permission(request) and self.has_delete_permission(request)

    @admin.action(description="Объединить компании (карточки перейдут на основную)", permissions=("merge",))
    def merge_companies_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[Company],
    ) -> None:
        """Merge selected legal entities into the oldest row."""
        companies = list(queryset.order_by("created_at", "pk"))
        if len(companies) < 2:
            self.message_user(
                request,
                _("Выберите хотя бы две компании для объединения."),
                messages.WARNING,
            )
            return
        target = companies[0]
        sources = companies[1:]
        from crm.company import merge_companies

        moved = merge_companies(target, sources, actor=request.user)
        self.message_user(
            request,
            _("Компании объединены в «%(name)s»: карточек %(clients)s, сотрудников %(members)s.")
            % {
                "name": target.name,
                "clients": moved["clients"],
                "members": moved["members"],
            },
            messages.SUCCESS,
        )

    @admin.display(description="сотрудников", ordering="_members_count")
    def members_count(self, obj: Company) -> int:
        count = getattr(obj, "_members_count", None)
        if count is not None:
            return int(count)
        return obj.members.count()

    @admin.display(description="карточек", ordering="_clients_count")
    def clients_count(self, obj: Company) -> int:
        count = getattr(obj, "_clients_count", None)
        if count is not None:
            return int(count)
        return obj.clients.count()

    def get_queryset(self, request: HttpRequest) -> QuerySet[Company]:
        from django.db.models import Count

        return (
            super()
            .get_queryset(request)
            .prefetch_related("work_labels")
            .annotate(
                _members_count=Count("members", distinct=True),
                _clients_count=Count("clients", distinct=True),
            )
        )

    @admin.display(description="отметки")
    def work_label_list(self, obj: Company) -> str:
        names = [label.name for label in obj.work_labels.all()]
        return ", ".join(names) if names else "—"

    @admin.action(description="Назначить меня ответственным", permissions=["change"])
    def assign_to_me(self, request: HttpRequest, queryset: QuerySet[Company]) -> None:
        """Reminders for planned calls use the company assignee when the event has none."""
        updated = queryset.update(assignee=request.user)
        self.message_user(request, f"Назначено компаний: {updated}.", messages.SUCCESS)
