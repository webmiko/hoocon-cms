"""Apply workbook profiles to a company card and remind assignees."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from config.logging_utils import setup_logger
from crm.models import Client, Company, PlannedTouch, PlannedTouchKind, WorkLabel
from crm.work_labels import WORK_LABEL_BY_CODE

logger = setup_logger("hoocon.crm")

_CALL_HOUR = 10
_LATE_HOURS = 6


@dataclass
class CompanyProfile:
    """Fields gathered from one workbook row, already normalized."""

    contact_name: str = ""
    phone: str = ""
    emails: str = ""
    website: str = ""
    city: str = ""
    niche: str = ""
    region: str = ""
    relevance: str = ""
    notes: str = ""
    label_codes: set[str] = field(default_factory=set)
    next_contact_on: date | None = None
    ogrn: str = ""


def ensure_work_labels() -> None:
    """Insert catalog marks that are not in the database yet."""
    from crm.work_labels import WORK_LABELS

    for spec in WORK_LABELS:
        WorkLabel.objects.get_or_create(
            code=spec.code,
            defaults={"name": spec.name, "kind": spec.kind, "sort": spec.sort, "is_active": True},
        )


def touch_dedupe_key(company_id: int, kind: str, day: date) -> str:
    """One planned call per company per day."""
    return f"company:{company_id}:{kind}:{day.isoformat()}"


def _append_unique(current: str, incoming: str, *, limit: int) -> str:
    text = (incoming or "").strip()
    if not text:
        return current
    if not current:
        return text[:limit]
    if text in current:
        return current
    joined = f"{current}; {text}"
    return joined[:limit]


def _append_note(current: str, incoming: str) -> str:
    text = (incoming or "").strip()
    if not text or text in (current or ""):
        return current
    if not current:
        return text
    return f"{current}\n\n{text}"


def apply_company_profile(org: Company, profile: CompanyProfile) -> int:
    """Fill empty company fields, add marks, and create a planned call.

    Existing text is kept. A second import of the same day does not add
    another planned call.

    Returns:
        1 when a planned call was created, else 0.
    """
    if profile.contact_name and not org.contact_name:
        org.contact_name = profile.contact_name[:200]
    org.phone = _append_unique(org.phone, profile.phone, limit=300)
    org.email = _append_unique(org.email, profile.emails, limit=300)
    if profile.website and not org.website:
        org.website = profile.website[:200]
    if profile.city and not org.city:
        org.city = profile.city[:80]
    if profile.niche and not org.niche:
        org.niche = profile.niche[:120]
    if profile.region and not org.region:
        org.region = profile.region[:40]
    if profile.relevance and not org.relevance:
        org.relevance = profile.relevance
    note = profile.notes
    if profile.ogrn and profile.ogrn not in (org.comment or ""):
        note = _append_note(note, f"ОГРН из файла: {profile.ogrn}")
    org.comment = _append_note(org.comment, note)
    if profile.next_contact_on and org.next_contact_at is None:
        org.next_contact_at = _at_call_hour(profile.next_contact_on)
    org.save()
    codes = [code for code in profile.label_codes if code in WORK_LABEL_BY_CODE]
    if codes:
        labels = list(WorkLabel.objects.filter(code__in=codes, is_active=True))
        if labels:
            org.work_labels.add(*labels)
    if profile.next_contact_on is None:
        return 0
    return _ensure_touch(org, profile)


def _at_call_hour(day: date) -> datetime:
    """10:00 in the project timezone. The workbook gives a date, not a clock time."""
    naive = datetime.combine(day, time(_CALL_HOUR, 0))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _ensure_touch(org: Company, profile: CompanyProfile) -> int:
    assert profile.next_contact_on is not None
    key = touch_dedupe_key(org.pk, PlannedTouchKind.CALL, profile.next_contact_on)
    if PlannedTouch.objects.filter(dedupe_key=key).exists():
        return 0
    script = profile.notes.strip()
    if len(script) > 2000:
        script = script[:2000]
    PlannedTouch.objects.create(
        company=org,
        assignee=cast(Any, org.assignee),
        kind=PlannedTouchKind.CALL,
        starts_at=_at_call_hour(profile.next_contact_on),
        title=f"Звонок: {org.name}"[:200],
        note=script,
        dedupe_key=key,
    )
    return 1


def _recipient(touch: PlannedTouch) -> Any | None:
    user: Any = touch.assignee
    company: Any = touch.company
    if user is None and touch.company_id and company is not None:
        user = company.assignee
    if user is None or not user.is_active or not user.is_staff:
        return None
    return user


def _is_due(touch: PlannedTouch, now: datetime) -> bool:
    remind = timedelta(minutes=min(touch.remind_before_minutes or 60, 24 * 60))
    return touch.starts_at - remind <= now < touch.starts_at + timedelta(hours=_LATE_HOURS)


def notify_due_touches(*, now: datetime | None = None) -> int:
    """Send due reminders. Returns how many events were delivered on at least one channel.

    An event with no assignee is skipped. A channel that is not configured
    (no email, MAX alerts off) is marked done so the beat does not retry it.
    A failed send stays unmarked and is tried again.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    moment = now or timezone.now()
    window_start = moment - timedelta(hours=_LATE_HOURS)
    window_end = moment + timedelta(hours=24)
    ids = list(
        PlannedTouch.objects.filter(starts_at__gt=window_start, starts_at__lte=window_end)
        .filter(Q(email_notified_at__isnull=True) | Q(max_notified_at__isnull=True))
        .filter(Q(assignee__isnull=False) | Q(company__assignee__isnull=False))
        .order_by("starts_at", "pk")
        .values_list("pk", flat=True)[:100],
    )
    user_model = get_user_model()
    delivered = 0
    for touch_id in ids:
        if _notify_one(touch_id, now=moment, user_model=user_model):
            delivered += 1
    return delivered


def _notify_one(touch_id: int, *, now: datetime, user_model: type[Any]) -> bool:
    from django.conf import settings
    from django.core.mail import send_mail
    from django.urls import reverse

    from accounts.max_alerts import format_staff_max_message, max_user_id_for, send_max_to_users

    with transaction.atomic():
        touch = (
            PlannedTouch.objects.select_for_update(of=("self",), skip_locked=True)
            .select_related("assignee", "company", "company__assignee")
            .filter(pk=touch_id)
            .first()
        )
        if touch is None or not _is_due(touch, now):
            return False
        user = _recipient(touch)
        if user is None:
            return False
        email_pending = touch.email_notified_at is None
        max_pending = touch.max_notified_at is None
        if not email_pending and not max_pending:
            return False
        when = timezone.localtime(touch.starts_at)
        company: Any = touch.company
        company_name = company.name if touch.company_id and company is not None else ""
        body = touch.note.strip() or touch.title
        try:
            path = reverse("admin:crm_plannedtouch_change", args=[touch.pk])
        except Exception:  # noqa: BLE001 — admin url may be absent in a partial app load
            path = ""
        text = format_staff_max_message(
            title=f"Звонок по плану: {when:%d.%m.%Y %H:%M}",
            body="\n".join(part for part in (company_name, body) if part),
            url=path,
        )
        recipient_email = (user.email or "").strip()
        recipient_pk = user.pk
        has_max = bool(max_user_id_for(user))

    user = user_model.objects.get(pk=recipient_pk)
    email_ok = True
    max_ok = True
    if email_pending and recipient_email:
        try:
            send_mail(
                subject=f"CRM: {touch.title}"[:200],
                message=text,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("planned_touch_email_failed pk=%s", touch_id)
            email_ok = False
    if max_pending and has_max:
        try:
            sent = send_max_to_users([user], text)
            max_ok = sent > 0
        except Exception:
            logger.exception("planned_touch_max_failed pk=%s", touch_id)
            max_ok = False
    with transaction.atomic():
        locked = PlannedTouch.objects.select_for_update().get(pk=touch_id)
        fields: list[str] = []
        if email_pending and email_ok and locked.email_notified_at is None:
            locked.email_notified_at = now
            fields.append("email_notified_at")
        if max_pending and max_ok and locked.max_notified_at is None:
            locked.max_notified_at = now
            fields.append("max_notified_at")
        if fields:
            locked.save(update_fields=fields)
    return bool(fields)


def remember_client_plan(client: Client, day: date | None) -> None:
    """Copy the planned day onto the contact card when it has no reminder yet."""
    if day is None or client.next_contact_at is not None:
        return
    client.next_contact_at = _at_call_hour(day)
    client.save(update_fields=["next_contact_at", "updated_at"])
