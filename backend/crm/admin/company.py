"""Company admin with member inline."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin
from crm.models import Company, CompanyMember


class CompanyMemberInline(TabularInline):
    """Members of a company card (CRM-x)."""

    model = CompanyMember
    extra = 1
    fields = ("client", "account", "role", "is_confirmed")
    autocomplete_fields = ("client",)


@admin.register(Company)
class CompanyAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Карточка юрлица: реквизиты + члены (целевая схема CRM-x)."""

    list_display = ("name", "inn", "members_count", "clients_count", "updated_at")
    list_display_links = ("name",)
    search_fields = ("name", "inn")
    readonly_fields = ("company_key", "created_at", "updated_at")
    inlines = (CompanyMemberInline,)
    actions = ("merge_companies_action",)

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
            .annotate(
                _members_count=Count("members", distinct=True),
                _clients_count=Count("clients", distinct=True),
            )
        )
