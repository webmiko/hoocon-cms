"""Views for the manager's «Мой день» page."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from crm.workspace import STALE_DAYS, build_workspace


def admin_landing(request: HttpRequest) -> HttpResponse:
    """``/admin/``: a working manager lands on «Мой день», everyone else on the panel.

    Only the bare address redirects. Mobile navigation and the desktop
    settings drill-down open the same page with ``?hoocon_*`` parameters
    and must keep getting the panel.
    """
    from accounts.roles import staff_sees_all_leads
    from config.unfold_callbacks import perm_view_workspace

    if (
        request.method == "GET"
        and not request.GET
        and request.user.is_authenticated
        and request.user.is_staff
        and not staff_sees_all_leads(request.user)
        and perm_view_workspace(request)
    ):
        return redirect("crm-workspace")
    return admin.site.admin_view(admin.site.index)(request)


def workspace_home(request: HttpRequest) -> HttpResponse:
    """The page a manager opens first: one queue, one starting point."""
    context = {
        **admin.site.each_context(request),
        "title": "Мой день",
        "workspace": build_workspace(request.user),
        "stale_days": STALE_DAYS,
    }
    return TemplateResponse(request, "admin/workspace.html", context)


@require_POST
def take_lead(request: HttpRequest, lead_id: int) -> HttpResponse:
    """Claim a lead from the queue and open it. Same rules as the list action."""
    from leads.models import Lead
    from leads.services import scope_leads_for_manager, take_lead_in_work

    if not request.user.has_perm("leads.change_lead"):
        raise PermissionDenied
    lead = scope_leads_for_manager(Lead.objects.filter(pk=lead_id), request.user).first()
    if lead is None:
        raise Http404
    _lead, taken = take_lead_in_work(lead, request.user)
    if not taken:
        messages.warning(request, "Эту заявку уже взял другой менеджер.")
        return redirect("crm-workspace")
    return redirect(reverse("admin:leads_lead_change", args=[lead.pk]))


def _company_for(request: HttpRequest, company_id: int) -> Any:
    """A firm the manager may open, or 404. Same scope as the «Клиенты» list."""
    from crm.models import Company
    from crm.services import scope_company_directory_for_manager

    company = scope_company_directory_for_manager(Company.objects.filter(pk=company_id), request.user).first()
    if company is None:
        raise Http404
    return company


def _back_to_company(company: Any) -> HttpResponse:
    return redirect(reverse("admin:crm_company_change", args=[company.pk]) + "#hoocon-card-top")


@require_POST
def company_next_step(request: HttpRequest, company_id: int) -> HttpResponse:
    """Set «Следующий шаг» with one click: завтра, через 3 дня, неделя…"""
    from crm.company_card import NEXT_STEP_CHOICES, next_step_target

    if not request.user.has_perm("crm.change_company"):
        raise PermissionDenied
    company = _company_for(request, company_id)
    allowed = {days for _label, days in NEXT_STEP_CHOICES}
    try:
        days = int(request.POST.get("days", ""))
    except ValueError:
        days = 0
    if request.POST.get("clear") == "1":
        company.next_contact_at = None
    elif days in allowed:
        company.next_contact_at = next_step_target(days)
    else:
        messages.error(request, "Выберите срок из списка.")
        return _back_to_company(company)
    company.save(update_fields=["next_contact_at", "updated_at"])
    messages.success(request, "Следующий шаг сохранён.")
    return _back_to_company(company)


@require_POST
def company_note(request: HttpRequest, company_id: int) -> HttpResponse:
    """Add a note to the firm's history without leaving the card."""
    from crm.company_card import primary_person
    from crm.models import Activity, ActivityType

    if not request.user.has_perm("crm.add_activity"):
        raise PermissionDenied
    company = _company_for(request, company_id)
    text = (request.POST.get("body") or "").strip()
    person = primary_person(company, request.user)
    if person is None:
        messages.error(
            request,
            "В фирме нет человека, которого вы ведёте. Добавьте человека в «Люди»: заметка хранится на нём.",
        )
    elif not text:
        messages.error(request, "Напишите, о чём говорили или что обещали.")
    else:
        Activity.objects.create(
            client=person,
            activity_type=ActivityType.NOTE,
            subject="Заметка",
            body=text[:5000],
            author=cast(Any, request.user),
        )
        messages.success(request, "Заметка сохранена.")
    return _back_to_company(company)


@require_POST
def company_call_result(request: HttpRequest, company_id: int) -> HttpResponse:
    """«Итог звонка»: one choice writes history, planned call and next step."""
    from crm.call_outcome import get_outcome, record_call_outcome
    from crm.company_card import NEXT_STEP_CHOICES

    if not (request.user.has_perm("crm.change_company") and request.user.has_perm("crm.add_activity")):
        raise PermissionDenied
    company = _company_for(request, company_id)
    outcome = get_outcome(request.POST.get("outcome", ""))
    if outcome is None:
        messages.error(request, "Выберите, чем закончился звонок.")
        return _back_to_company(company)
    allowed = {days for _label, days in NEXT_STEP_CHOICES}
    raw_days = (request.POST.get("days") or "").strip()
    days: int | None = None
    if raw_days:
        try:
            days = int(raw_days)
        except ValueError:
            days = None
        if days not in allowed:
            messages.error(request, "Выберите срок из списка.")
            return _back_to_company(company)
    recorded = record_call_outcome(company, request.user, outcome, days=days, note=request.POST.get("note", ""))
    parts = [f"Итог записан: {outcome.label}."]
    if recorded.next_contact_at is not None:
        parts.append(f"Вернуться к клиенту: {timezone.localtime(recorded.next_contact_at):%d.%m в %H:%M}.")
    if not recorded.logged:
        parts.append(
            "В историю запись не попала: в фирме нет человека, которого вы ведёте"
            + (", поэтому текст не сохранён." if request.POST.get("note", "").strip() else "."),
        )
    messages.success(request, " ".join(parts))
    if outcome.key == "need_quote":
        from crm.company_card import primary_person

        person = primary_person(company, request.user)
        if person is not None and request.user.has_perm("crm.add_quote"):
            return redirect(reverse("admin:crm_quote_add") + f"?client={person.pk}")
    return _back_to_company(company)


@require_POST
def close_lead(request: HttpRequest, lead_id: int) -> HttpResponse:
    """Close a lead from its page. Only its manager (or the head of sales) may.

    A free lead is taken first: closing it would silently make the closer its
    manager. The check runs under a row lock, so a parallel «Взять» is not lost.
    """
    from accounts.roles import staff_sees_all_leads
    from leads.models import Lead
    from leads.services import scope_leads_for_manager, set_lead_status

    if not request.user.has_perm("leads.change_lead"):
        raise PermissionDenied
    visible = scope_leads_for_manager(Lead.objects.filter(pk=lead_id), request.user).first()
    if visible is None:
        raise Http404
    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=visible.pk)
        if lead.assignee_id != request.user.pk and not staff_sees_all_leads(request.user):
            messages.warning(
                request,
                "Закрыть заявку может её менеджер. Сначала возьмите заявку в работу."
                if lead.assignee_id is None
                else "Эту заявку ведёт другой менеджер.",
            )
            return redirect(reverse("admin:leads_lead_change", args=[lead.pk]))
        _lead, error = set_lead_status(lead, status=Lead.LeadStatus.DONE, actor=request.user)
    if error:
        messages.warning(request, "Не удалось закрыть заявку.")
    else:
        messages.success(request, "Заявка закрыта.")
    return redirect(reverse("admin:leads_lead_change", args=[lead.pk]))


@require_POST
def person_note(request: HttpRequest, person_id: int) -> HttpResponse:
    """Add a note to one contact from the top of their card."""
    from crm.models import Activity, ActivityType, Client
    from crm.services import scope_clients_for_manager

    if not request.user.has_perm("crm.add_activity"):
        raise PermissionDenied
    person = scope_clients_for_manager(Client.objects.filter(pk=person_id), request.user).first()
    if person is None:
        raise Http404
    text = (request.POST.get("body") or "").strip()
    if not text:
        messages.error(request, "Напишите, о чём говорили или что обещали.")
    else:
        Activity.objects.create(
            client=person,
            activity_type=ActivityType.NOTE,
            subject="Заметка",
            body=text[:5000],
            author=cast(Any, request.user),
        )
        messages.success(request, "Заметка сохранена.")
    return redirect(reverse("admin:crm_client_change", args=[person.pk]) + "#hoocon-person-top")


def _chat_or_404(chat_id: int) -> Any:
    from supportchat.models import Conversation

    return get_object_or_404(Conversation.objects.select_related("assignee", "client", "lead"), pk=chat_id)


@require_POST
def take_chat(request: HttpRequest, chat_id: int) -> HttpResponse:
    """Claim a free open dialog. Two clicks at once: the first one wins."""
    from supportchat.models import Conversation, ConversationStatus
    from supportchat.staff_actions import assign_conversation

    if not request.user.has_perm("supportchat.change_conversation"):
        raise PermissionDenied
    chat = _chat_or_404(chat_id)
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=chat.pk)
        if locked.status == ConversationStatus.CLOSED:
            messages.warning(request, "Диалог уже закрыт.")
        elif locked.assignee_id not in (None, request.user.pk):
            messages.warning(request, "Этот диалог уже ведёт другой менеджер.")
        elif locked.assignee_id is None:
            assign_conversation(locked, cast(Any, request.user), actor=cast(Any, request.user))
            messages.success(request, "Диалог ваш. Ответьте клиенту.")
    return redirect(reverse("admin:supportchat_conversation_change", args=[chat.pk]))


@require_POST
def close_chat(request: HttpRequest, chat_id: int) -> HttpResponse:
    """Close a dialog and ask the client for a rating once, like the list action does."""
    from supportchat.models import Conversation, ConversationStatus
    from supportchat.rating import request_client_rating

    if not request.user.has_perm("supportchat.change_conversation"):
        raise PermissionDenied
    chat = _chat_or_404(chat_id)
    closed_now = False
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=chat.pk)
        if locked.assignee_id not in (None, request.user.pk) and not request.user.is_superuser:
            messages.warning(request, "Этот диалог ведёт другой менеджер.")
            return redirect(reverse("admin:supportchat_conversation_change", args=[chat.pk]))
        if locked.status != ConversationStatus.CLOSED:
            locked.status = ConversationStatus.CLOSED
            locked.save(update_fields=["status", "updated_at"])
            closed_now = True
    if closed_now:
        request_client_rating(locked)
        messages.success(request, "Диалог закрыт.")
    return redirect(reverse("admin:supportchat_conversation_changelist"))


@require_POST
def quote_answer(request: HttpRequest, quote_id: int) -> HttpResponse:
    """«Клиент согласился / отказался» in one click, with the usual status rules."""
    from crm.models import Quote, QuoteStatus
    from crm.quote_ops import transition_quote
    from crm.services import scope_quotes_for_manager

    if not request.user.has_perm("crm.change_quote"):
        raise PermissionDenied
    quote = scope_quotes_for_manager(Quote.objects.filter(pk=quote_id), request.user).first()
    if quote is None:
        raise Http404
    status = request.POST.get("answer", "")
    if status not in (QuoteStatus.ACCEPTED, QuoteStatus.REJECTED):
        messages.error(request, "Неизвестный ответ клиента.")
    else:
        _result, error = transition_quote(quote, status, actor=request.user)
        if error:
            messages.error(request, "Из текущего статуса так перевести КП нельзя.")
        elif status == QuoteStatus.ACCEPTED:
            messages.success(request, "Клиент согласился. Ниже кнопка «Создать заказ».")
        else:
            messages.success(request, "Отказ записан. Для новой версии нажмите «Копия черновиком».")
    return redirect(reverse("admin:crm_quote_change", args=[quote.pk]))
