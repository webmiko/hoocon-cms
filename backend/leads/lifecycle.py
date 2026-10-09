"""What happens after any new Lead row: routing, emails, staff alerts.

Every entry point (public form, cabinet repeat, spec → lead) calls
:func:`on_lead_created` so no channel silently skips the manager.
"""

from __future__ import annotations

from django.db import transaction

from config.logging_utils import setup_logger
from leads.models import Lead
from leads.services import assign_lead_on_create
from leads.tasks import send_lead_client_confirmation, send_lead_notification

logger = setup_logger("hoocon.leads")


def _enqueue_staff_push(lead_id: int) -> None:
    try:
        from accounts.tasks import notify_staff_max_new_lead, notify_staff_telegram_new_lead
        from staff_api.tasks import notify_staff_fcm_new_lead
        from webpush.tasks import notify_staff_new_lead

        notify_staff_fcm_new_lead.delay(lead_id)
        notify_staff_new_lead.delay(lead_id)
        notify_staff_telegram_new_lead.delay(lead_id)
        notify_staff_max_new_lead.delay(lead_id)
    except Exception:  # noqa: BLE001 — optional broker/app may be absent
        logger.exception("lead_staff_push_enqueue_failed lead_id=%s", lead_id)


def on_lead_created(lead: Lead) -> None:
    """Assign a manager now; email sales + client and push staff after commit."""
    assign_lead_on_create(lead)
    lead_id = lead.pk
    transaction.on_commit(lambda: send_lead_notification.delay(lead_id))
    transaction.on_commit(lambda: send_lead_client_confirmation.delay(lead_id))
    transaction.on_commit(lambda: _enqueue_staff_push(lead_id))
    # PII-safe log: only lead_id and type (NO email/phone).
    logger.info("Lead created: lead_id=%s type=%s", lead_id, lead.lead_type)
