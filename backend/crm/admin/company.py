"""Company admin with member inline."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from accounts.roles import staff_sees_all_leads
from config.admin_mixins import OpenChangeLinkMixin
from config.admin_toggle import LabeledToggleMixin
from crm.admin.filters import WorkQueueFilter
from crm.admin.inline_extra import OneBlankInlineRowMixin
from crm.admin.list_view import remember_list_view
from crm.admin.work_label_form import WorkLabelAssignableFormMixin
from crm.models import Client, Company, CompanyMember, PlannedTouch
from crm.phone_widget import MultiPhoneWidget


def _manager_may_add_to_company(user: Any, company: Company | None) -> bool:
    """Contacts and planned calls are added on a free company or on one's own.

    Reading another manager's rows is already hidden by the queryset. This
    stops a new row on a company that already has an owner.
    """
    if company is None or company.pk is None:
        return True
    if staff_sees_all_leads(user):
        return True
    return company.assignee_id in (None, getattr(user, "pk", None))


class CompanyClientInline(OneBlankInlineRowMixin, TabularInline):
    """People of this company. The contact card opens from the row link."""

    model = Client
    fk_name = "company_ref"
    fields = ("name", "email", "phone", "assignee")
    autocomplete_fields = ("assignee",)
    show_change_link = True
    can_delete = False
    verbose_name = "контакт"
    verbose_name_plural = "контакты"

    def get_queryset(self, request: HttpRequest) -> QuerySet[Client]:
        """A manager edits only the contacts already on their own list."""
        from crm.services import scope_clients_for_manager

        return scope_clients_for_manager(super().get_queryset(request), request.user)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """No new contact on a company that already belongs to someone else."""
        if not super().has_add_permission(request, obj):
            return False
        return _manager_may_add_to_company(request.user, obj)


class CompanyCallInline(OneBlankInlineRowMixin, TabularInline):
    """Planned calls live on the company, not in a separate daily section."""

    model = PlannedTouch
    fk_name = "company"
    fields = ("starts_at", "status", "assignee", "title")
    autocomplete_fields = ("assignee",)
    show_change_link = True
    verbose_name = "плановый звонок"
    verbose_name_plural = "плановые звонки"

    def get_queryset(self, request: HttpRequest) -> QuerySet[PlannedTouch]:
        """Another manager's calls are not on this card and are not saved from it."""
        from crm.services import scope_planned_touches_for_manager

        return scope_planned_touches_for_manager(super().get_queryset(request), request.user)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """No new planned call on a company that already belongs to someone else."""
        if not super().has_add_permission(request, obj):
            return False
        return _manager_may_add_to_company(request.user, obj)


class CompanyMemberInline(LabeledToggleMixin, OneBlankInlineRowMixin, TabularInline):
    """Members of a company card (CRM-x)."""

    model = CompanyMember
    toggle_labels = {"is_confirmed": ("Не подтверждён", "Подтверждён")}
    fields = ("client", "account", "role", "is_confirmed")
    autocomplete_fields = ("client",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[CompanyMember]:
        """Hide members whose contact card the manager cannot open."""
        from crm.services import scope_clients_for_manager

        qs = super().get_queryset(request)
        scoped = scope_clients_for_manager(Client.objects.all(), request.user)
        return qs.filter(Q(client_id__isnull=True) | Q(client_id__in=scoped.values("pk")))

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        """A posted client pk must be one this manager may already see."""
        if db_field.name == "client":
            from crm.services import scope_clients_for_manager

            kwargs["queryset"] = scope_clients_for_manager(Client.objects.all(), request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """No new cabinet member on a company that already belongs to someone else."""
        if not super().has_add_permission(request, obj):
            return False
        return _manager_may_add_to_company(request.user, obj)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Confirmation of a member on someone else's company is not this manager's write."""
        if not super().has_change_permission(request, obj):
            return False
        return _manager_may_add_to_company(request.user, obj)


class CompanyAdminForm(forms.ModelForm):
    """Phone is one input per number. The column still stores them together."""

    class Meta:
        model = Company
        fields = "__all__"
        widgets = {"phone": MultiPhoneWidget()}


@admin.register(Company)
class CompanyAdmin(WorkLabelAssignableFormMixin, OpenChangeLinkMixin, ModelAdmin):
    """Карточка юрлица: реквизиты + члены (целевая схема CRM-x)."""

    form = CompanyAdminForm
    list_before_template = "admin/includes/hoocon_page_memo.html"

    list_display = ("name", "inn", "city", "relevance", "work_label_list", "next_contact_at", "assignee")
    list_display_links = ("name",)
    list_filter = ("relevance", "region", "niche", WorkQueueFilter, "assignee", "work_labels")
    search_fields = ("name", "inn", "city", "phone", "email", "website", "contact_name")
    autocomplete_fields = ("assignee",)
    filter_horizontal = ()
    readonly_fields = ("company_key", "created_at", "updated_at")
    inlines = (CompanyClientInline, CompanyCallInline, CompanyMemberInline)
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
        extra.update(remember_list_view(request))
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

    def get_readonly_fields(self, request: HttpRequest, obj: Company | None = None) -> tuple[str, ...]:
        """The assignee of someone else's company is not a field a manager can post."""
        readonly = tuple(super().get_readonly_fields(request, obj))
        if obj is None or obj.pk is None or staff_sees_all_leads(request.user):
            return readonly
        if obj.assignee_id not in (None, request.user.pk):
            return (*readonly, "assignee")
        return readonly

    def save_model(self, request: HttpRequest, obj: Company, form: Any, change: bool) -> None:
        """Keep the stored owner when a manager saves a company that is not theirs."""
        if change and obj.pk and not staff_sees_all_leads(request.user):
            stored_id = Company.objects.filter(pk=obj.pk).values_list("assignee_id", flat=True).first()
            if stored_id not in (None, request.user.pk):
                obj.assignee_id = stored_id
        super().save_model(request, obj, form, change)

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
        """Claim a company with no manager. One that already has an owner stays theirs."""
        mine = getattr(request.user, "pk", None)
        claimable = queryset.none()
        if mine is not None:
            claimable = queryset.filter(Q(assignee_id=None) | Q(assignee_id=mine))
        updated = claimable.update(assignee=request.user)
        self.message_user(request, f"Назначено компаний: {updated}.", messages.SUCCESS)
