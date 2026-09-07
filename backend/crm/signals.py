"""Signals: auto-link Lead → Client on create; inbound activity trail."""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from config.logging_utils import setup_logger
from leads.models import Lead

logger = setup_logger("hoocon.crm")


@receiver(post_save, sender=Lead)
def link_new_lead_to_client(
    sender: type[Lead],  # noqa: ARG001
    instance: Lead,
    created: bool,
    **kwargs: object,
) -> None:
    """On new Lead, create/find Client, link, and log inbound Activity.

    Args:
        sender: Lead model class.
        instance: saved Lead.
        created: True on insert.
    """
    if not created:
        return
    from crm.models import Activity, ActivityType
    from crm.services import link_lead_to_client

    try:
        if not instance.client_id:
            link_lead_to_client(instance)
        client_id = instance.client_id
        if not client_id:
            return
        Activity.objects.create(
            client_id=client_id,
            lead=instance,
            activity_type=ActivityType.NOTE,
            subject=f"Входящая заявка #{instance.pk}: {instance.get_lead_type_display()}",
            body=(instance.message or "")[:2000],
        )
    except (DatabaseError, IntegrityError):
        logger.exception("crm_link_lead_failed lead_id=%s", instance.pk)


@receiver(post_save, sender="crm.Activity")
def notify_superuser_on_staff_activity(
    sender: type,  # noqa: ARG001
    instance: object,
    created: bool,
    **kwargs: object,
) -> None:
    """Telegram superusers when a staff-authored CRM Activity is created."""
    if not created:
        return
    author_id = getattr(instance, "author_id", None)
    if not author_id:
        return
    subject = (getattr(instance, "subject", "") or "").strip()
    activity_type = getattr(instance, "get_activity_type_display", None)
    type_label = activity_type() if callable(activity_type) else "Активность"
    client_id = getattr(instance, "client_id", None)
    pk = getattr(instance, "pk", None)
    body = f"{type_label}: {subject or f'#{pk}'}"
    url = f"/admin/crm/client/{client_id}/change/" if client_id else "/admin/crm/client/"

    def _enqueue() -> None:
        from accounts.tasks import notify_superuser_telegram_crm

        notify_superuser_telegram_crm.delay("CRM: активность", body, url)

    transaction.on_commit(_enqueue)
