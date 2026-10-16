"""Admin queue. Access is decided here, not by a branch in another widget."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline

from staffrequests.models import (
    StaffRequest,
    StaffRequestReply,
    StaffRequestSettings,
    StaffRequestStatus,
)
from staffrequests.services import can_file, can_manage_queue, can_toggle, requests_enabled

_CLOSED = frozenset({StaffRequestStatus.DONE, StaffRequestStatus.REJECTED})


def app_home(request: HttpRequest) -> HttpResponse:
    """App index only lists this queue. Open the queue itself."""
    return HttpResponseRedirect(reverse("admin:staffrequests_staffrequest_changelist"))


class StaffRequestReplyInline(TabularInline):
    """Replies on the request. Empty extra row is not stored.

    Permissions are not the Django defaults: managers have no model grant
    for this inline, and the parent admin already decided who may open the card.
    """

    model = StaffRequestReply
    extra = 1
    can_delete = False
    fields = ("body", "author", "created_at")
    readonly_fields = ("author", "created_at")

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """The parent card is the gate. The inline is visible with it."""
        return True

    def has_add_permission(self, request: HttpRequest, obj: Any) -> bool:
        """A new reply can be added on a card the user is allowed to open."""
        return True

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """An existing reply stays as it was written."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Replies are not removed."""
        return False


@admin.register(StaffRequest)
class StaffRequestAdmin(ModelAdmin):
    """Managers see their own cards. Admins see the queue and set status."""

    change_list_template = "admin/staffrequests/change_list.html"
    list_display = ("title", "kind", "status", "author", "created_at")
    list_filter = ("status", "kind")
    search_fields = ("title", "body")

    def get_inlines(
        self,
        request: HttpRequest,
        obj: StaffRequest | None = None,
    ) -> tuple[type[StaffRequestReplyInline], ...]:
        """Replies start after the card exists. The add form stays three fields."""
        if obj is None:
            return ()
        return (StaffRequestReplyInline,)

    def get_urls(self) -> list[Any]:
        """Toggle lives on this admin so telephony save code stays untouched."""
        custom = [
            path(
                "toggle/",
                self.admin_site.admin_view(self.toggle_view),
                name="staffrequests_staffrequest_toggle",
            ),
        ]
        return custom + super().get_urls()

    def toggle_view(self, request: HttpRequest) -> HttpResponse:
        """Switch the widget. Off hides the menu and refuses new cards."""
        if request.method != "POST" or not can_toggle(request.user):
            raise PermissionDenied
        row = StaffRequestSettings.load()
        row.enabled = request.POST.get("enabled") == "on"
        row.save(update_fields=["enabled"])
        if row.enabled:
            messages.success(request, "Техподдержка включена.")
        else:
            messages.success(request, "Техподдержка выключена.")
        return HttpResponseRedirect(reverse("admin:sitesettings_sitesettings_changelist"))

    def has_module_permission(self, request: HttpRequest) -> bool:
        """Hidden from the admin index while the widget is off."""
        return requests_enabled() and can_file(request.user)

    def has_view_permission(self, request: HttpRequest, obj: StaffRequest | None = None) -> bool:
        """A manager opens only a card they wrote."""
        if not requests_enabled() or not can_file(request.user):
            return False
        if obj is None or can_manage_queue(request.user):
            return True
        return obj.author_id == request.user.pk

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Nobody files a request while the widget is off."""
        return requests_enabled() and can_file(request.user)

    def has_change_permission(self, request: HttpRequest, obj: StaffRequest | None = None) -> bool:
        """Same gate as view: own card, or the whole queue for an admin."""
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: StaffRequest | None = None) -> bool:
        """History stays. Close a request instead of deleting it."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[StaffRequest]:
        """Admins see every row. A manager's list is only their own."""
        qs = super().get_queryset(request).select_related("author")
        if can_manage_queue(request.user):
            return qs
        return qs.filter(author=request.user)

    def get_fields(self, request: HttpRequest, obj: StaffRequest | None = None) -> tuple[str, ...]:
        """Status appears after the card exists. The author does not pick it on create."""
        if obj is None:
            return ("kind", "title", "body")
        return ("kind", "title", "body", "status", "author", "closed_at")

    def get_readonly_fields(self, request: HttpRequest, obj: StaffRequest | None = None) -> tuple[str, ...]:
        """Managers cannot edit the card or the status after it is filed."""
        if obj is None:
            return ()
        if can_manage_queue(request.user):
            return ("author", "closed_at")
        return ("kind", "title", "body", "status", "author", "closed_at")

    def save_model(self, request: HttpRequest, obj: StaffRequest, form: Any, change: bool) -> None:
        """Stamp the author. Ignore a manager's attempt to close the card."""
        if not change:
            author_pk = getattr(request.user, "pk", None)
            if not isinstance(author_pk, int):
                raise PermissionDenied
            obj.author_id = author_pk
            obj.status = StaffRequestStatus.NEW
        elif not can_manage_queue(request.user):
            stored = StaffRequest.objects.get(pk=obj.pk)
            obj.kind = stored.kind
            obj.title = stored.title
            obj.body = stored.body
            obj.status = stored.status
            obj.author_id = stored.author_id
        if obj.status in _CLOSED:
            if obj.closed_at is None:
                obj.closed_at = timezone.now()
        else:
            obj.closed_at = None
        super().save_model(request, obj, form, change)

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        """New replies belong to the person who submitted the form."""
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, StaffRequestReply):
                text = (obj.body or "").strip()
                if not text:
                    continue
                obj.body = text
                if obj.author_id is None:
                    author_pk = getattr(request.user, "pk", None)
                    if not isinstance(author_pk, int):
                        raise PermissionDenied
                    obj.author_id = author_pk
            obj.save()
        formset.save_m2m()

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Counts follow the same queryset as the list (own cards, or the whole queue)."""
        extra = dict(extra_context or {})
        if self.has_view_permission(request):
            counts = {
                row["status"]: row["n"] for row in self.get_queryset(request).values("status").annotate(n=Count("id"))
            }
            extra["request_stats"] = " · ".join(
                f"{label} {counts.get(value, 0)}" for value, label in StaffRequestStatus.choices
            )
        return super().changelist_view(request, extra_context=extra)
