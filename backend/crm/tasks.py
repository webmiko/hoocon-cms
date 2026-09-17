"""Celery tasks for CRM outbound email."""

from __future__ import annotations

from celery import shared_task
from django.core.mail import EmailMessage as DjangoEmailMessage

from config.logging_utils import setup_logger
from crm.models import EmailMessage, EmailStatus

logger = setup_logger("hoocon.crm")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_crm_email(self: object, email_id: int) -> None:
    """Send a queued CRM EmailMessage via Django SMTP.

    Args:
        self: Celery task instance.
        email_id: EmailMessage primary key.

    Note:
        Logs only email_id and status — never full recipient PII.
    """
    try:
        msg = EmailMessage.objects.select_related("client").get(pk=email_id)
    except EmailMessage.DoesNotExist:
        logger.warning("crm_email_missing id=%s", email_id)
        return

    if msg.status == EmailStatus.SENT:
        return

    try:
        django_msg = DjangoEmailMessage(
            subject=msg.subject,
            body=msg.body,
            from_email=msg.from_email,
            to=[msg.to_email],
        )
        reply_to = (msg.reply_to_email or "").strip()
        if reply_to:
            django_msg.reply_to = [reply_to]
        django_msg.send(fail_silently=False)
    except Exception as exc:
        logger.exception("crm_email_send_failed id=%s", email_id)
        msg.mark_failed(f"{type(exc).__name__}")
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    msg.mark_sent()
    logger.info("crm_email_sent id=%s", email_id)
