"""Signals: auto-link Lead → Client on create; inbound activity trail."""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError
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
