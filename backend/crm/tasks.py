"""Celery tasks for CRM outbound email."""

from __future__ import annotations

from celery import shared_task
from django.core.mail import EmailMessage as DjangoEmailMessage
from django.core.mail import EmailMultiAlternatives

from config.logging_utils import setup_logger
from crm.email_body import html_email_to_plain, is_html_email_body
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
        reply_to = (msg.reply_to_email or "").strip()
        django_msg: EmailMultiAlternatives | DjangoEmailMessage
        if is_html_email_body(msg.body):
            django_msg = EmailMultiAlternatives(
                subject=msg.subject,
                body=html_email_to_plain(msg.body),
                from_email=msg.from_email,
                to=[msg.to_email],
            )
            django_msg.attach_alternative(msg.body, "text/html")
        else:
            django_msg = DjangoEmailMessage(
                subject=msg.subject,
                body=msg.body,
                from_email=msg.from_email,
                to=[msg.to_email],
            )
        if reply_to:
            django_msg.reply_to = [reply_to]
            # Lead «Ответить клиенту»: BCC manager so the thread starts in their mailbox.
            if msg.lead_id and reply_to.casefold() != (msg.to_email or "").strip().casefold():
                django_msg.bcc = [reply_to]
        django_msg.send(fail_silently=False)
    except Exception as exc:
        logger.exception("crm_email_send_failed id=%s", email_id)
        msg.mark_failed(f"{type(exc).__name__}")
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    msg.mark_sent()
    logger.info("crm_email_sent id=%s", email_id)
