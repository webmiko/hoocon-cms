"""Celery tasks for leads: email notification on new lead (PII-safe logging).

Spec: ПЛАН §6 Iter 3 — Celery email; docs/security-baseline.md §3 (PII не в логах).

Контракт:
- send_lead_notification(lead_id): отправляет email менеджеру на
  LEAD_NOTIFY_EMAIL (из settings). Тело письма содержит данные заявки
  (для менеджера — это нормально), но логи Celery НЕ содержат PII
  (email/phone клиента).
- Вызов через transaction.on_commit в view — задача стартует только
  после коммита транзакции (нет гонок при откате).
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template import (
    Context,
    Template,  # type: ignore[attr-defined]
)

from leads.models import Lead

logger = logging.getLogger("hoocon.leads")

# Email body template (plain text; rendered with lead context for the manager).
_EMAIL_SUBJECT_TEMPLATE = "Новая заявка #{lead_id}: {lead_type_display} от {name}"

_EMAIL_BODY_TEMPLATE = Template(
    """
Поступила новая заявка с сайта Hoocon.

Тип: {{ lead.lead_type_display }}
Имя: {{ lead.name }}
Компания: {{ lead.company|default:"—" }}
Email: {{ lead.email }}
Телефон: {{ lead.phone|default:"—" }}
{% if lead.sku %}SKU: {{ lead.sku.sku_code }} ({{ lead.sku.name }}){% endif %}
{% if lead.quantity %}Количество: {{ lead.quantity }}{% endif %}
{% if lead.analog_belimo_code %}Аналог Belimo: {{ lead.analog_belimo_code }}{% endif %}

Сообщение:
{{ lead.message }}

—
Заявка создана: {{ lead.created_at|date:"Y-m-d H:i" }}
Обработайте в Admin: /admin/leads/lead/{{ lead.pk }}/change/
""".strip(),
)


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
        lead = Lead.objects.get(pk=lead_id)
    except Lead.DoesNotExist:
        logger.warning("Lead not found: lead_id=%s (skipping notification)", lead_id)
        return

    notify_email = getattr(settings, "LEAD_NOTIFY_EMAIL", "")
    if not notify_email:
        logger.warning("LEAD_NOTIFY_EMAIL not set; skipping lead_id=%s", lead_id)
        return

    subject = _EMAIL_SUBJECT_TEMPLATE.format(
        lead_id=lead.pk,
        lead_type_display=lead.get_lead_type_display(),
        name=lead.name,
    )
    body = _EMAIL_BODY_TEMPLATE.render(Context({"lead": lead}))

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notify_email],
            fail_silently=False,
        )
    except Exception as exc:
        # PII-safe log: only lead_id and type, never email/phone.
        logger.exception(
            "Failed to send lead notification: lead_id=%s type=%s",
            lead_id,
            lead.lead_type,
        )
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    # Success log — NO PII (email/phone), only lead_id and type.
    logger.info(
        "Lead notification sent: lead_id=%s type=%s",
        lead_id,
        lead.lead_type,
    )
