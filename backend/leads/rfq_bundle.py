"""RFQ soft-bundle: group leads by normalized company + name."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from leads.models import Lead

# Open RFQs with the same key within this window share one thread.
RFQ_BUNDLE_WINDOW_DAYS = 14

_MAX_KEY_LEN = 400


def normalize_rfq_name(raw: str) -> str:
    """Strip, collapse spaces, casefold for RFQ bundle matching."""
    return " ".join((raw or "").split()).casefold()


def normalize_rfq_company(raw: str) -> str:
    """Strip, collapse spaces, casefold for RFQ bundle matching."""
    return " ".join((raw or "").split()).casefold()


def build_rfq_bundle_key(*, company: str, name: str) -> str:
    """Return ``company|name`` key or empty if either side is blank."""
    company_n = normalize_rfq_company(company)
    name_n = normalize_rfq_name(name)
    if not company_n or not name_n:
        return ""
    key = f"{company_n}|{name_n}"
    return key[:_MAX_KEY_LEN]


def resolve_open_bundle_root(key: str, *, exclude_pk: int | None = None) -> Lead | None:
    """Oldest open RFQ with ``key`` in the window (effective root).

    If a candidate points at a done root, the open candidate itself is used
    so the thread continues without attaching to a closed lead.
    """
    if not key:
        return None
    since = timezone.now() - timedelta(days=RFQ_BUNDLE_WINDOW_DAYS)
    qs = Lead.objects.filter(
        lead_type=Lead.LeadType.RFQ,
        rfq_bundle_key=key,
        status__in=(Lead.LeadStatus.NEW, Lead.LeadStatus.IN_PROGRESS),
        created_at__gte=since,
    ).order_by("created_at", "pk")
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    for cand in qs.iterator():
        root = cand.rfq_bundle_root
        if root is None:
            return cand
        if root.status in (Lead.LeadStatus.NEW, Lead.LeadStatus.IN_PROGRESS):
            return root
        return cand
    return None


def attach_rfq_bundle(lead: Lead) -> None:
    """Set ``rfq_bundle_key`` / ``rfq_bundle_root`` for an RFQ lead.

    Non-RFQ leads clear the key. Call after the lead row exists (has pk).
    """
    if lead.lead_type != Lead.LeadType.RFQ:
        if lead.rfq_bundle_key or lead.rfq_bundle_root_id:
            lead.rfq_bundle_key = ""
            lead.rfq_bundle_root = None
            lead.save(update_fields=["rfq_bundle_key", "rfq_bundle_root", "updated_at"])
        return

    key = build_rfq_bundle_key(company=lead.company, name=lead.name)
    root = resolve_open_bundle_root(key, exclude_pk=lead.pk)
    lead.rfq_bundle_key = key
    lead.rfq_bundle_root = root
    lead.save(update_fields=["rfq_bundle_key", "rfq_bundle_root", "updated_at"])


def rfq_bundle_queryset(lead: Lead) -> QuerySet[Lead]:
    """Root + siblings for Admin thread display."""
    if lead.rfq_bundle_root_id:
        root_id = lead.rfq_bundle_root_id
    else:
        root_id = lead.pk
    return Lead.objects.filter(
        Q(pk=root_id) | Q(rfq_bundle_root_id=root_id),
    ).order_by("created_at", "pk")


def mark_rfq_bundle_done(lead: Lead, *, actor: object) -> int:
    """Mark open leads in the thread as done; return count updated."""
    from leads.services import (
        apply_lead_manager_on_save,
        log_manager_activity,
        manager_display_name,
    )

    now = timezone.now()
    count = 0
    for sibling in rfq_bundle_queryset(lead):
        if sibling.status == Lead.LeadStatus.DONE:
            continue
        sibling.status = Lead.LeadStatus.DONE
        apply_lead_manager_on_save(sibling, actor=actor)
        if sibling.processed_at is None:
            sibling.processed_at = now
        sibling.save()
        log_manager_activity(
            sibling,
            author=actor,
            subject=f"Нить КП завершена: {manager_display_name(actor)}",
            body="Статус → Завершена (нить КП)",
        )
        count += 1
    return count
