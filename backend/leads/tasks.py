"""Celery tasks for leads: email notification on new lead (PII-safe logging).

Spec: ПЛАН §6 Iter 3 — Celery email; docs/security-baseline.md §3 (PII не в логах).

Контракт:
- send_lead_notification(lead_id): multipart email получателям из
  resolve_lead_notify_recipients (sales@ или User.email менеджера).
  Тело — для менеджера (с PII), логи Celery — только lead_id + lead_type.
- send_lead_client_confirmation(lead_id): клиенту «заявка принята в работу»
  (to=lead.email, Reply-To — почта менеджера или sales-ящик).
- Вызов через transaction.on_commit в view.
"""

from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from config.logging_utils import setup_logger
from leads.models import Lead
from leads.services import (
    render_lead_client_confirmation,
    render_lead_notification,
    resolve_lead_notify_recipients,
    resolve_lead_reply_to,
)

logger = setup_logger("hoocon.leads")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_lead_notification(self: object, lead_id: int) -> None:
    """Send a notification email about a new lead to the sales team.

    Args:
        self: the Celery task instance (bind=True).
        lead_id: primary key of the newly created Lead.

    Note:
        Logs only lead_id and lead_type (NO PII — email/phone never logged).
        Retries up to 3 times with 60s backoff on transient SMTP errors.
    """
    try:
        lead = Lead.objects.select_related("sku", "assignee").get(pk=lead_id)
    except Lead.DoesNotExist:
        logger.warning("Lead not found: lead_id=%s (skipping notification)", lead_id)
        return

    recipients = resolve_lead_notify_recipients(lead)
    if not recipients:
        logger.warning("No lead notify recipients; skipping lead_id=%s", lead_id)
        return

    subject, text_body, html_body = render_lead_notification(lead)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(html_body, "text/html")

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        # PII-safe log: only lead_id and type, never email/phone.
        logger.exception(
            "Failed to send lead notification: lead_id=%s type=%s",
            lead_id,
            lead.lead_type,
        )
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    logger.info(
        "Lead notification sent: lead_id=%s type=%s recipients=%s",
        lead_id,
        lead.lead_type,
        len(recipients),
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_lead_client_confirmation(self: object, lead_id: int) -> None:
    """Send «заявка принята в работу» email to the client (to=lead.email).

    Args:
        self: the Celery task instance (bind=True).
        lead_id: primary key of the newly created Lead.

    Note:
        Reply-To points at the assignee mailbox (or LEAD_NOTIFY_EMAIL
        fallback), so the client can answer the confirmation directly.
        Logs only lead_id (NO PII). Retries up to 3 times with 60s backoff.
    """
    try:
        lead = Lead.objects.select_related("assignee").get(pk=lead_id)
    except Lead.DoesNotExist:
        logger.warning("Lead not found: lead_id=%s (skipping client confirmation)", lead_id)
        return

    client_email = (lead.email or "").strip()
    if not client_email:
        logger.warning("Lead has no client email; skipping confirmation lead_id=%s", lead_id)
        return

    subject, text_body, html_body = render_lead_client_confirmation(lead)
    reply_to = resolve_lead_reply_to(lead)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[client_email],
        reply_to=[reply_to] if reply_to else [],
    )
    message.attach_alternative(html_body, "text/html")

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Failed to send lead client confirmation: lead_id=%s", lead_id)
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    logger.info("Lead client confirmation sent: lead_id=%s", lead_id)
