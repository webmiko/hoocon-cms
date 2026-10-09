"""Celery tasks for the client cabinet (OTP email, staff alerts)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_client_otp_email_task(self: object, email: str, code: str) -> None:
    """Send the client-cabinet OTP code; retries on transient SMTP errors.

    Logs only the masked recipient (no code, no full email — PII-safe).
    """
    from cabinet.services import build_client_otp_message
    from config.admin_otp import mask_email

    try:
        build_client_otp_message(email, code).send(fail_silently=False)
    except Exception as exc:
        logger.exception("Client OTP email failed: to=%s", mask_email(email))
        raise self.retry(exc=exc)  # type: ignore[attr-defined]
    logger.info("Client OTP email sent: to=%s", mask_email(email))


def rma_notify_recipients(case: object) -> list[str]:
    """Client card owner (active staff with email), else the sales list."""
    from leads.services import parse_notify_emails

    client = getattr(case, "client", None)
    owner = getattr(client, "assignee", None)
    if owner is not None and owner.is_active and owner.is_staff and (owner.email or "").strip():
        return parse_notify_emails(owner.email)
    return parse_notify_emails(getattr(settings, "LEAD_NOTIFY_EMAIL", "") or "")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_staff_new_rma(self: object, case_id: int) -> None:
    """Email the manager about a reclamation filed from the cabinet.

    The cabinet promises «менеджер свяжется» — without this nobody knew.
    """
    from django.core.mail import EmailMultiAlternatives
    from django.urls import reverse

    from cabinet.models import RmaCase

    case = RmaCase.objects.select_related("client__assignee", "order").filter(pk=case_id).first()
    if case is None:
        return
    recipients = rma_notify_recipients(case)
    if not recipients:
        logger.warning("No RMA notify recipients; skipping case_id=%s", case_id)
        return
    site = (getattr(settings, "SITE_URL", "") or "https://hoocon.ru").rstrip("/")
    admin_url = site + reverse("admin:cabinet_rmacase_change", args=[case.pk])
    client = case.client
    lines = [
        f"Клиент: {client.name or client.email} ({client.email})",
        f"Тема: {case.subject}",
        f"Серийный номер: {case.serial_number or '—'}",
        f"Заказ: {case.order.number if case.order else '—'}",
        "",
        case.description or "",
        "",
        f"Открыть: {admin_url}",
    ]
    message = EmailMultiAlternatives(
        subject=f"Рекламация #{case.pk}: {case.subject}"[:200],
        body="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("RMA notification failed: case_id=%s", case_id)
        raise self.retry(exc=exc)  # type: ignore[attr-defined]
    logger.info("RMA notification sent: case_id=%s recipients=%s", case_id, len(recipients))
