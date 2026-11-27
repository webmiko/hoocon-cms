"""One-touch result of a call: what happened and when to come back.

After a call the manager does three things in the standard admin: add an
activity, change the planned call status, set the next contact date. Most
of them skip at least one, so the card lies and the client is lost.

This service does all three from one choice and keeps the data coherent:
the history gets a line, the planned call leaves the «Сегодня» queue or
moves to the next try, and the firm gets a next step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from crm.company_card import next_step_target, primary_person
from crm.models import Activity, ActivityType, PlannedTouch, PlannedTouchStatus


@dataclass(frozen=True)
class Outcome:
    """A possible result of a call."""

    key: str
    label: str
    hint: str
    # Days to the next try when the manager chose no date; None = leave as is.
    default_days: int | None
    touch_status: str
    # Move the open planned call to the next try instead of closing it.
    reschedule: bool = False


OUTCOMES: tuple[Outcome, ...] = (
    Outcome("reached", "Дозвонился", "Поговорили", None, PlannedTouchStatus.REACHED),
    Outcome("no_answer", "Не дозвонился", "Не взяли трубку", 1, PlannedTouchStatus.NO_ANSWER, reschedule=True),
    Outcome("callback", "Просил перезвонить", "Назначим время", 1, PlannedTouchStatus.RESCHEDULED, reschedule=True),
    Outcome("need_quote", "Нужно КП", "Готовим предложение", None, PlannedTouchStatus.REACHED),
)
_BY_KEY = {outcome.key: outcome for outcome in OUTCOMES}
# Planned calls still waiting for a result.
_OPEN_STATUSES = (
    PlannedTouchStatus.PLANNED,
    PlannedTouchStatus.IN_PROGRESS,
    PlannedTouchStatus.NO_ANSWER,
    PlannedTouchStatus.RESCHEDULED,
)


def get_outcome(key: str) -> Outcome | None:
    return _BY_KEY.get(key)


@dataclass(frozen=True)
class Recorded:
    """What the call result changed, for the message to the manager."""

    outcome: Outcome
    logged: bool
    next_contact_at: datetime | None
    touches: int


def record_call_outcome(
    company: Any,
    user: Any,
    outcome: Outcome,
    *,
    days: int | None = None,
    note: str = "",
    now: datetime | None = None,
) -> Recorded:
    """Write the result of a call into history, planned calls and next step."""
    now = now or timezone.now()
    chosen = days if days is not None else outcome.default_days
    target = next_step_target(chosen, now=now) if chosen is not None else None
    person = primary_person(company, user)
    with transaction.atomic():
        logged = False
        if person is not None:
            Activity.objects.create(
                client=person,
                activity_type=ActivityType.CALL,
                subject=f"Звонок: {outcome.label}",
                body=note.strip()[:5000],
                author=user,
            )
            logged = True
        touches = _close_planned_calls(company, user, outcome, target, now)
        if target is not None:
            company.next_contact_at = target
            company.save(update_fields=["next_contact_at", "updated_at"])
    return Recorded(outcome=outcome, logged=logged, next_contact_at=target, touches=touches)


def _close_planned_calls(company: Any, user: Any, outcome: Outcome, target: datetime | None, now: datetime) -> int:
    """Settle the due planned calls of this firm that ``user`` may touch.

    A free firm can hold a colleague's planned call: it is theirs and stays
    untouched. Meetings and other kinds are not calls, so they stay too.
    «Reached» closes every due call (old duplicates included). «No answer»
    and «call back» move only the latest due call to the next try.
    """
    from crm.models import PlannedTouchKind
    from crm.services import scope_planned_touches_for_manager

    end_of_today = (timezone.localtime(now) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    queryset = scope_planned_touches_for_manager(
        PlannedTouch.objects.filter(
            company=company,
            kind=PlannedTouchKind.CALL,
            status__in=_OPEN_STATUSES,
            starts_at__lt=end_of_today,
        ),
        user,
    ).order_by("-starts_at", "-pk")
    touches = list(queryset)
    if outcome.reschedule and target is not None:
        touches = touches[:1]
    for touch in touches:
        touch.status = outcome.touch_status
        update = ["status"]
        if outcome.reschedule and target is not None:
            touch.starts_at = target
            update.append("starts_at")
            # A moved call is a new reminder: the old «sent» marks no longer apply.
            touch.email_notified_at = None
            touch.max_notified_at = None
            update += ["email_notified_at", "max_notified_at"]
        touch.save(update_fields=update)
    return len(touches)


FINISH_OUTCOME = Outcome("finish", "Завершено", "Закрыто вручную", None, PlannedTouchStatus.DONE)


def settle_planned_calls(company: Any, user: Any, outcome: Outcome, *, now: datetime | None = None) -> int:
    """Close the due planned calls of this firm that ``user`` may touch, without a new date."""
    return _close_planned_calls(company, user, outcome, None, now or timezone.now())


def reschedule_due_calls(company: Any, user: Any, target: datetime, *, now: datetime | None = None) -> int:
    """A newer agreement replaces the overdue planned calls of this firm.

    The latest due call moves to ``target``; older due duplicates are closed,
    so none of them keeps reading as «overdue» after the manager moved the date.
    """
    from crm.models import PlannedTouchKind
    from crm.services import scope_planned_touches_for_manager

    now = now or timezone.now()
    end_of_today = (timezone.localtime(now) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    touches = list(
        scope_planned_touches_for_manager(
            PlannedTouch.objects.filter(
                company=company,
                kind=PlannedTouchKind.CALL,
                status__in=_OPEN_STATUSES,
                starts_at__lt=end_of_today,
            ),
            user,
        ).order_by("-starts_at", "-pk"),
    )
    for index, touch in enumerate(touches):
        if index == 0:
            touch.status = PlannedTouchStatus.RESCHEDULED
            touch.starts_at = target
            touch.email_notified_at = None
            touch.max_notified_at = None
            touch.save(update_fields=["status", "starts_at", "email_notified_at", "max_notified_at"])
        else:
            touch.status = PlannedTouchStatus.DONE
            touch.save(update_fields=["status"])
    return len(touches)
