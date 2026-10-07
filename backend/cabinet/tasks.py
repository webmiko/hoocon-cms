"""Celery tasks for the client cabinet (OTP email delivery)."""

from __future__ import annotations

import logging

from celery import shared_task

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
