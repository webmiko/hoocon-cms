"""Email messages, templates, attachments and mailbox state admin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from config.admin_mixins import OpenChangeLinkMixin, ScopedForeignKeyMixin
from config.unfold_callbacks import _versioned_static
from crm.admin.filters import EmailAuthorFilter
from crm.admin.scope import _CLIENT_AND_LEAD, ManagerUsesTheCard
from crm.email_body import email_body_for_reading
from crm.models import Client, EmailAttachment, EmailMessage, EmailStatus, EmailTemplate, InboundMailboxState
from crm.services import email_templates_for_user, scope_emails_for_manager
from leads.models import Lead
from leads.services import lead_visible_to_manager, manager_display_name


class EmailAttachmentInline(TabularInline):
    """Read-only attachments of an inbound message (private download)."""

    model = EmailAttachment
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = False
    fields = ("download_link", "content_type", "size")
    readonly_fields = fields
    verbose_name = "вложение"
    verbose_name_plural = "вложения"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Attachments arrive via IMAP only — no manual add."""
        return False

    @admin.display(description="файл")
    def download_link(self, obj: EmailAttachment) -> str:
        """Staff download link through the scoped admin view."""
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:crm_emailattachment_download", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.filename)


class EmailMessageAdminForm(forms.ModelForm):
    """Letter card shows and stores readable text, not HTML source."""

    class Meta:
        model = EmailMessage
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.is_bound or "body" not in self.fields:
            return
        self.initial["body"] = email_body_for_reading(self.initial.get("body") or "")

    def clean_body(self) -> str:
        """Drop tags if the manager pasted HTML into the card."""
        return email_body_for_reading(self.cleaned_data.get("body") or "")


@admin.register(EmailMessage)
class EmailMessageAdmin(ManagerUsesTheCard, ScopedForeignKeyMixin, OpenChangeLinkMixin, ModelAdmin):
    """Outbound/inbound email log; staff can resend failed/draft.

    ID = email клиента (или to_email); одинаковые ID группируются.
    """

    form = EmailMessageAdminForm
    inlines = (EmailAttachmentInline,)

    list_display = (
        "client_email_id",
        "direction",
        "status",
        "to_email",
        "subject",
        "client",
        "created_at",
        "sent_at",
    )
    list_display_links = ("subject",)
    list_filter = (EmailAuthorFilter, "direction", "status", "created_at")
    search_fields = ("subject", "to_email", "from_email", "client__name", "client__email", "body")
    autocomplete_fields = ("client", "lead", "created_by")
    scoped_fk = _CLIENT_AND_LEAD

    class Media:
        """«Заявка» autocomplete фильтруется по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

    readonly_fields = (
        "direction",
        "from_email",
        "error_message",
        "created_at",
        "sent_at",
        "created_by",
        "message_id",
        "in_reply_to",
        "imap_uid",
        "mailbox",
        "received_at",
    )
    ordering = ("client__email", "-created_at")
    actions = ("queue_send",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "client",
                    "lead",
                    "direction",
                    "status",
                    "to_email",
                    "from_email",
                    "reply_to_email",
                    "subject",
                    "body",
                ),
            },
        ),
        (
            "Доставка",
            {
                "fields": ("error_message", "created_by", "created_at", "sent_at"),
            },
        ),
        (
            "Технические",
            {
                "fields": ("message_id", "in_reply_to", "imap_uid", "mailbox", "received_at"),
            },
        ),
    )

    @admin.display(description="ID", ordering="client__email")
    def client_email_id(self, obj: EmailMessage) -> str:
        """Group key: client email (fallback to to_email)."""
        if obj.client_id:
            return cast(Client, obj.client).email
        return (obj.to_email or "").strip().lower() or "—"

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailMessage]:
        """Prefetch client; scope rows for managers."""
        qs = super().get_queryset(request).select_related("client", "lead", "created_by")
        return scope_emails_for_manager(qs, request.user)

    @admin.action(description=_("Отправить выбранные (очередь)"), permissions=("change",))
    def queue_send(
        self,
        request: HttpRequest,
        queryset: Any,
    ) -> None:
        """Enqueue drafts, failures, and QUEUED rows whose send went stale.

        Uses transaction.on_commit so Celery never races the DB commit.
        """
        from crm.services import enqueue_crm_email
        from crm.tasks import email_send_is_stale

        count = 0
        for msg in queryset:
            statuses: tuple[str, ...] = (EmailStatus.DRAFT, EmailStatus.FAILED)
            if msg.status == EmailStatus.QUEUED and email_send_is_stale(msg.pk):
                statuses = (EmailStatus.QUEUED,)
            elif msg.status == EmailStatus.SENDING and email_send_is_stale(msg.pk):
                statuses = (EmailStatus.SENDING,)
            elif msg.status not in statuses:
                continue
            updated = EmailMessage.objects.filter(
                pk=msg.pk,
                status__in=statuses,
            ).update(status=EmailStatus.QUEUED)
            if not updated:
                continue
            enqueue_crm_email(msg.pk)
            count += 1
        skipped = queryset.count() - count
        self.message_user(
            request,
            _("В очередь: %(n)s. Пропущено: %(skip)s.") % {"n": count, "skip": skipped},
            messages.SUCCESS if count else messages.WARNING,
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: EmailMessage,
        form: Any,
        change: bool,
    ) -> None:
        """On create, set created_by; enqueue only on transition to QUEUED."""
        from crm.services import enqueue_crm_email

        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        lead = cast(Lead | None, obj.lead) if obj.lead_id else None
        if not lead_visible_to_manager(lead, request.user):
            raise PermissionDenied(_("Нельзя привязать письмо к чужой заявке."))
        previous_status = None
        if change and obj.pk:
            previous_status = EmailMessage.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        super().save_model(request, obj, form, change)
        became_queued = obj.status == EmailStatus.QUEUED and (not change or previous_status != EmailStatus.QUEUED)
        if became_queued:
            enqueue_crm_email(obj.pk)


@dataclass(frozen=True)
class TemplateAudience:
    """Who may see a template: every manager, or the checked people."""

    everyone: bool
    user_ids: frozenset[int]


class TemplateAudienceWidget(forms.Widget):
    """«Всем менеджерам» plus one checkbox per manager."""

    managers: list[tuple[int, str]]

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        super().__init__(attrs)
        self.managers = []
        self.locked = False

    def value_from_datadict(self, data: Any, files: Any, name: str) -> dict[str, Any]:
        """Read the everyone flag and the checked manager ids."""
        everyone = str(data.get(f"{name}_all") or "") == "1"
        getter = getattr(data, "getlist", None)
        raw = getter(name) if callable(getter) else data.get(name, [])
        if raw is None:
            raw = []
        if isinstance(raw, str):
            raw = [raw]
        return {"everyone": everyone, "ids": list(raw)}

    def render(
        self,
        name: str,
        value: Any,
        attrs: dict[str, Any] | None = None,
        renderer: Any = None,
    ) -> SafeString:
        """Stack the everyone checkbox above the manager list."""
        everyone, selected = _audience_state(value)
        base_id = (attrs or {}).get("id") or name
        rows = [
            format_html(
                '<label class="flex items-center gap-2" for="{}"><input type="checkbox" name="{}_all" '
                'id="{}" value="1"{}> Всем менеджерам</label>',
                f"{base_id}_all",
                name,
                f"{base_id}_all",
                _box_flags(checked=everyone, locked=self.locked),
            )
        ]
        for user_id, label in self.managers:
            rows.append(
                format_html(
                    '<label class="flex items-center gap-2" for="{}"><input type="checkbox" name="{}" '
                    'id="{}" value="{}"{}> {}</label>',
                    f"{base_id}_{user_id}",
                    name,
                    f"{base_id}_{user_id}",
                    user_id,
                    _box_flags(checked=user_id in selected, locked=self.locked),
                    label,
                )
            )
        if self.locked:
            rows.extend(_locked_audience_inputs(name, everyone, selected))
        body = mark_safe("".join(str(row) for row in rows))
        return format_html('<div class="flex flex-col gap-2 py-1">{}</div>', body)


class TemplateAudienceField(forms.Field):
    """Validate that a restricted template names real managers."""

    widget: TemplateAudienceWidget
    manager_ids: set[int]

    def __init__(self, **kwargs: Any) -> None:
        kwargs["widget"] = TemplateAudienceWidget()
        super().__init__(**kwargs)
        self.manager_ids = set()

    def set_managers(self, managers: list[tuple[int, str]]) -> None:
        """Replace the checkbox list. Ids outside it are rejected."""
        self.manager_ids = {user_id for user_id, _label in managers}
        self.widget.managers = managers

    def lock(self, locked: bool) -> None:
        """Disabled boxes still display the audience. Hidden inputs keep a text save intact."""
        self.widget.locked = locked

    def to_python(self, value: Any) -> TemplateAudience:
        """Turn the posted checkboxes into an audience."""
        if isinstance(value, TemplateAudience):
            return value
        if not isinstance(value, dict):
            return TemplateAudience(everyone=True, user_ids=frozenset())
        ids: list[int] = []
        for item in value.get("ids") or []:
            text = str(item).strip()
            if not text.isdigit():
                raise ValidationError("В списке только действующие менеджеры.")
            ids.append(int(text))
        return TemplateAudience(everyone=bool(value.get("everyone")), user_ids=frozenset(ids))

    def validate(self, value: TemplateAudience) -> None:
        """«Всем» needs no names. A short list must be managers, and not empty."""
        super().validate(value)
        if value.everyone:
            return
        if value.user_ids - self.manager_ids:
            raise ValidationError("В списке только действующие менеджеры.")
        if not value.user_ids:
            raise ValidationError("Отметьте «Всем менеджерам» или хотя бы одного человека.")


def _box_flags(*, checked: bool, locked: bool) -> SafeString:
    """Attribute text for one checkbox. Constants only, so the string is safe."""
    flags = ""
    if checked:
        flags += " checked"
    if locked:
        flags += " disabled"
    return mark_safe(flags)


def _locked_audience_inputs(name: str, everyone: bool, selected: set[int]) -> list[SafeString]:
    """Post the current audience when the visible boxes are disabled."""
    if everyone:
        return [format_html('<input type="hidden" name="{}_all" value="1">', name)]
    return [format_html('<input type="hidden" name="{}" value="{}">', name, user_id) for user_id in sorted(selected)]


def _audience_state(value: Any) -> tuple[bool, set[int]]:
    """Checked boxes for the first paint and for a form that failed validation."""
    if isinstance(value, TemplateAudience):
        return value.everyone, set(value.user_ids)
    if isinstance(value, dict):
        selected: set[int] = set()
        for item in value.get("ids") or []:
            text = str(item).strip()
            if text.isdigit():
                selected.add(int(text))
        return bool(value.get("everyone")), selected
    return True, set()


def _may_assign_template_author(user: Any) -> bool:
    """Superuser and group «Админ» may name who owns a template.

    A manager's new template is theirs. An analyst sees every template
    but does not reassign it.
    """
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    return groups.filter(name=GROUP_ADMIN).exists()


def _author_queryset(request: HttpRequest) -> QuerySet[Any]:
    """Managers, plus the current user and the saved author so the choice stays valid."""
    user_model = get_user_model()
    managers = user_model.objects.filter(is_active=True, is_staff=True, groups__name=GROUP_MANAGER)
    extra = [request.user.pk]
    match = getattr(request, "resolver_match", None)
    object_id = ""
    if match is not None:
        object_id = str(match.kwargs.get("object_id") or "")
    if object_id.isdigit():
        current = EmailTemplate.objects.filter(pk=int(object_id)).values_list("created_by_id", flat=True).first()
        if current:
            extra.append(current)
    return (
        user_model.objects.filter(Q(pk__in=managers.values("pk")) | Q(pk__in=extra))
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def _audience_managers(extra_ids: list[int]) -> list[tuple[int, str]]:
    """Active managers, plus anyone already checked so they can be unchecked."""
    user_model = get_user_model()
    managers = user_model.objects.filter(is_active=True, is_staff=True, groups__name=GROUP_MANAGER)
    people = user_model.objects.filter(Q(pk__in=managers.values("pk")) | Q(pk__in=extra_ids)).distinct()
    rows = list(people.order_by("first_name", "last_name", "username"))
    return [(user.pk, manager_display_name(user)) for user in rows]


class EmailTemplateAdminForm(forms.ModelForm):
    """Pick every manager or a named list. A colleague cannot rewrite that list."""

    audience = TemplateAudienceField(
        label="Кому видно",
        required=False,
        help_text=(
            "«Всем менеджерам» — шаблон виден каждому, включая новых. "
            "Иначе — только отмеченным: отметьте и себя, если он нужен вам. "
            "Администратор и аналитик видят все шаблоны. "
            "Состав меняет автор шаблона или администратор."
        ),
    )

    class Meta:
        model = EmailTemplate
        exclude = ("visibility", "visible_to")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        extra_ids: list[int] = []
        if self.instance.pk:
            extra_ids = list(self.instance.visible_to.values_list("pk", flat=True))
        audience = cast(TemplateAudienceField, self.fields["audience"])
        audience.set_managers(_audience_managers(extra_ids))
        audience.lock(not self._may_edit_audience())
        if not self.is_bound:
            restricted = self.instance.pk and self.instance.visibility == EmailTemplate.Visibility.SELECTED
            self.initial["audience"] = TemplateAudience(
                everyone=not restricted,
                user_ids=frozenset(extra_ids) if restricted else frozenset(),
            )

    def clean(self) -> dict[str, Any]:
        """Keep a shared or foreign list as it is, unless the author or an admin edits it."""
        cleaned = super().clean()
        if cleaned is None:
            return {}
        audience = cleaned.get("audience")
        if not isinstance(audience, TemplateAudience):
            return cleaned
        if audience.everyone:
            audience = TemplateAudience(everyone=True, user_ids=frozenset())
            cleaned["audience"] = audience
        if self._may_edit_audience() or audience == self._stored_audience():
            return cleaned
        self.add_error("audience", "Круг людей меняет автор шаблона или администратор.")
        return cleaned

    def _may_edit_audience(self) -> bool:
        """New templates, the creator, and an admin may change who sees it."""
        if not self.instance.pk:
            return True
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if _may_assign_template_author(user):
            return True
        return self.instance.created_by_id == user.pk

    def _stored_audience(self) -> TemplateAudience:
        """Audience already saved on this row."""
        if not self.instance.pk or self.instance.visibility != EmailTemplate.Visibility.SELECTED:
            return TemplateAudience(everyone=True, user_ids=frozenset())
        ids = frozenset(self.instance.visible_to.values_list("pk", flat=True))
        return TemplateAudience(everyone=False, user_ids=ids)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    """Reusable email presets: picked via «Шаблон» on compose forms."""

    form = EmailTemplateAdminForm
    list_display = ("name", "subject", "audience_label", "is_active", "sort_order", "created_by", "updated_at")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "visibility")
    search_fields = ("name", "subject", "body")
    readonly_fields = ("created_by", "created_at", "updated_at")
    ordering = ("sort_order", "name")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "created_by", "audience", "is_active", "sort_order", "subject", "body"),
                "description": (
                    "Плейсхолдеры {имя}, {компания}, {почта}, {телефон}, {заказ} "
                    "подставляются из карточки клиента или заявки. "
                    "{заказ} — сообщение и позиции заявки; в письме с карточки клиента берётся последняя заявка. "
                    "«Автор» — кому принадлежит шаблон: этот человек меняет, кому он виден. "
                    "Поле выбирает администратор. «Кому видно»: всем менеджерам или отмеченным людям."
                ),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: EmailTemplate | None = None,
    ) -> list[str] | tuple[str, ...]:
        """Managers see the author. An admin can set it when creating a template for someone."""
        readonly = list(super().get_readonly_fields(request, obj))
        if _may_assign_template_author(request.user):
            return [name for name in readonly if name != "created_by"]
        if "created_by" not in readonly:
            readonly.append("created_by")
        return readonly

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        """Author choices are active managers, not every user in the database."""
        if db_field.name == "created_by":
            kwargs["queryset"] = _author_queryset(request)
            kwargs["help_text"] = (
                "Кому принадлежит шаблон. Этот человек меняет, кому он виден. "
                "Пустое поле при сохранении оставляет шаблон за вами."
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(
        self,
        request: HttpRequest,
        obj: EmailTemplate | None = None,
        **kwargs: Any,
    ) -> type[EmailTemplateAdminForm]:
        """Bind the current user so visibility checks know the author."""
        form_class = super().get_form(request, obj, **kwargs)

        class EmailTemplateRequestForm(form_class):  # type: ignore[valid-type,misc]
            def __init__(self, *args: Any, **form_kwargs: Any) -> None:
                self.request = request
                super().__init__(*args, **form_kwargs)

        return EmailTemplateRequestForm

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailTemplate]:
        """Managers see shared templates and ones they are checked on. Unscoped staff see all."""
        qs = super().get_queryset(request).select_related("created_by").prefetch_related("visible_to")
        return email_templates_for_user(request.user, qs)

    @admin.display(description="кому видно")
    def audience_label(self, obj: EmailTemplate) -> str:
        """«Всем менеджерам» or the checked names."""
        if obj.visibility != EmailTemplate.Visibility.SELECTED:
            return "Всем менеджерам"
        names = sorted(manager_display_name(user) for user in obj.visible_to.all())
        return ", ".join(names) if names else "—"

    def save_model(
        self,
        request: HttpRequest,
        obj: EmailTemplate,
        form: Any,
        change: bool,
    ) -> None:
        """A blank author on the first save is the person saving. The checkbox list sets who sees it."""
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        audience = form.cleaned_data.get("audience")
        if isinstance(audience, TemplateAudience):
            obj.visibility = EmailTemplate.Visibility.ALL if audience.everyone else EmailTemplate.Visibility.SELECTED
        super().save_model(request, obj, form, change)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        """Store the checked managers. «Всем» clears the list so new managers stay included."""
        super().save_related(request, form, formsets, change)
        audience = form.cleaned_data.get("audience")
        if not isinstance(audience, TemplateAudience):
            return
        if audience.everyone:
            form.instance.visible_to.clear()
        else:
            form.instance.visible_to.set(audience.user_ids)


@admin.register(EmailAttachment)
class EmailAttachmentAdmin(ModelAdmin):
    """Attachment registry; files live in PRIVATE_MEDIA_ROOT (no public URL)."""

    list_display = ("email", "filename", "content_type", "size", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("filename", "email__subject", "email__from_email")
    readonly_fields = ("email", "filename", "content_type", "size", "file", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Attachments arrive via IMAP only."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailAttachment]:
        """Scope attachments to messages visible to the manager."""
        qs = super().get_queryset(request).select_related("email", "email__client")
        visible = scope_emails_for_manager(
            EmailMessage.objects.all(),
            request.user,
        ).values("pk")
        return qs.filter(email_id__in=visible)

    def get_urls(self) -> list[Any]:
        """Add scoped staff download endpoint."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/download/",
                self.admin_site.admin_view(self.download_view),
                name="crm_emailattachment_download",
            ),
        ]
        return custom + urls

    def download_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Serve the file only when the parent email is in manager scope."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(EmailAttachment, pk=pk)
        visible = scope_emails_for_manager(
            EmailMessage.objects.filter(pk=obj.email_id),
            request.user,
        ).exists()
        if not visible:
            raise PermissionDenied(_("Нет доступа к вложению этого письма."))
        return FileResponse(
            open(obj.file.path, "rb"),
            as_attachment=True,
            filename=obj.filename,
        )


@admin.register(InboundMailboxState)
class InboundMailboxStateAdmin(ModelAdmin):
    """IMAP cursor + fetch health (singleton; read-only for staff)."""

    list_display = ("folder", "last_uid", "last_run_at", "last_error")
    readonly_fields = ("folder", "last_uid", "last_run_at", "last_error")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Singleton row is created by the fetch task."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Cursor row must not be removed."""
        return False
