"""CRM services: find/create Client from Lead, queue outbound email."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from config.logging_utils import setup_logger
from crm.models import (
    Activity,
    ActivityType,
    Client,
    EmailDirection,
    EmailMessage,
    EmailStatus,
)
from leads.models import Lead

logger = setup_logger("hoocon.crm")


def normalize_client_email(raw: str) -> str:
    """Normalize email for Client dedup (strip + lower).

    Args:
        raw: raw email string.

    Returns:
        Normalized email.
    """
    return (raw or "").strip().lower()


def normalize_client_name(raw: str) -> str:
    """Normalize contact name for comparison (strip + collapse spaces)."""
    return " ".join((raw or "").split())


def normalize_client_company(raw: str) -> str:
    """Normalize company for comparison (strip + collapse spaces)."""
    return " ".join((raw or "").split())


def contact_matches_client(
    client: Client,
    *,
    email: str,
    name: str,
    company: str,
) -> bool:
    """True when email (ID) matches and name/company are the same profile.

    Empty company on either side still matches on email + name when the
    other side is empty (first lead without company).

    Args:
        client: existing CRM card.
        email: normalized lead email.
        name: normalized lead name.
        company: normalized lead company.

    Returns:
        Whether this lead belongs to the same client card.
    """
    if normalize_client_email(client.email) != email:
        return False
    client_name = normalize_client_name(client.name)
    if client_name and name and client_name.casefold() != name.casefold():
        return False
    client_company = normalize_client_company(client.company)
    if client_company and company and client_company.casefold() != company.casefold():
        return False
    return True


def find_client_for_lead(lead: Lead) -> Client | None:
    """Find existing Client by email (ID); prefer name/company match.

    Email is the unique card key: several leads with the same email always
    map to one Client. When several cards somehow share an email prefix
    search, prefer the row whose name and company also match.

    Args:
        lead: Lead with contact fields.

    Returns:
        Matching Client or None.
    """
    email = normalize_client_email(lead.email)
    if not email:
        return None
    candidates = list(Client.objects.filter(email=email))
    if not candidates:
        return None
    name = normalize_client_name(lead.name)
    company = normalize_client_company(lead.company)
    for client in candidates:
        if contact_matches_client(client, email=email, name=name, company=company):
            return client
    # Same email ID → always the same card (unique constraint).
    return candidates[0]


def get_or_create_client_from_lead(lead: Lead) -> Client:
    """Find Client by email (ID) or create from Lead contact fields.

    Multiple requests with the same email attach to one client card.
    Name/company are used for profile match and to fill empty fields.

    Args:
        lead: saved Lead instance.

    Returns:
        Client linked (or to be linked) to this lead.
    """
    email = normalize_client_email(lead.email)
    existing = find_client_for_lead(lead)
    if existing is not None:
        return _merge_lead_contact_into_client(existing, lead)

    defaults = {
        "name": normalize_client_name(lead.name) or email,
        "phone": lead.phone or "",
        "company": normalize_client_company(lead.company),
    }
    try:
        with transaction.atomic():
            client, created = Client.objects.get_or_create(
                email=email,
                defaults=defaults,
            )
    except IntegrityError:
        client = Client.objects.get(email=email)
        created = False

    if not created:
        return _merge_lead_contact_into_client(client, lead)
    return client


def _merge_lead_contact_into_client(client: Client, lead: Lead) -> Client:
    """Attach lead contact data to an existing card without duplicating it.

    Fills empty phone/company/name; does not overwrite filled fields when
    the lead brings a different name/company (same email = same client).
    """
    updated = False
    if not client.phone and lead.phone:
        client.phone = lead.phone
        updated = True
    lead_company = normalize_client_company(lead.company)
    if not client.company and lead_company:
        client.company = lead_company
        updated = True
    lead_name = normalize_client_name(lead.name)
    if lead_name and (
        not client.name
        or client.name == client.email
        or normalize_client_name(client.name).casefold() == lead_name.casefold()
    ):
        if client.name != lead_name:
            client.name = lead_name
            updated = True
    if updated:
        client.save()
    return client


def link_lead_to_client(lead: Lead) -> Client:
    """Ensure Lead.client is set; reuse Client card for the same email ID.

    Args:
        lead: Lead to attach.

    Returns:
        The Client instance.
    """
    if lead.client_id:
        return lead.client  # type: ignore[return-value]
    client = get_or_create_client_from_lead(lead)
    Lead.objects.filter(pk=lead.pk).update(client_id=client.pk)
    lead.client_id = client.pk
    lead.client = client
    return client


def enqueue_crm_email(email_id: int) -> None:
    """Schedule Celery send after the current DB transaction commits.

    Args:
        email_id: EmailMessage primary key.
    """
    from crm.tasks import send_crm_email

    def _enqueue() -> None:
        send_crm_email.delay(email_id)

    transaction.on_commit(_enqueue)


def create_outbound_email(
    *,
    client: Client,
    subject: str,
    body: str,
    to_email: str | None = None,
    lead: Lead | None = None,
    author: AbstractBaseUser | None = None,
    send_now: bool = True,
) -> EmailMessage:
    """Create an outbound EmailMessage and optionally queue send.

    Args:
        client: CRM client.
        subject: email subject.
        body: plain-text body.
        to_email: override recipient (default client.email).
        lead: optional related Lead.
        author: staff User who composed the message.
        send_now: enqueue Celery send after commit.

    Returns:
        Created EmailMessage (status DRAFT or QUEUED).
    """
    from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "webmaster@localhost"
    created_by = author if author is not None and author.is_authenticated else None
    msg = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED if send_now else EmailStatus.DRAFT,
        to_email=(to_email or client.email).strip(),
        from_email=from_addr,
        subject=subject.strip(),
        body=body.strip(),
        created_by=created_by,  # type: ignore[misc]
    )
    Activity.objects.create(
        client=client,
        lead=lead,
        activity_type=ActivityType.EMAIL,
        subject=msg.subject,
        body=msg.body[:2000],
        author=created_by,  # type: ignore[misc]
    )
    if send_now:
        enqueue_crm_email(msg.pk)
    return msg


def scope_clients_for_manager(queryset: QuerySet[Client], user: Any) -> QuerySet[Client]:
    """Limit CRM clients for a non-superuser manager.

    Superuser / «Админ» / «Аналитик» see all. Otherwise visible when: assigned
    to the manager, linked to a scoped lead, or the manager authored an
    activity on the card (timeline access without unlocking foreign leads —
    Lead inline stays scoped separately).

    Args:
        queryset: base Client queryset.
        user: authenticated staff user.

    Returns:
        Filtered Client queryset.
    """
    from accounts.roles import staff_sees_all_leads
    from leads.services import scope_leads_for_manager

    if staff_sees_all_leads(user):
        return queryset
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return queryset.none()

    scoped_lead_ids = scope_leads_for_manager(Lead.objects.all(), user).values("pk")
    return queryset.filter(
        Q(assignee_id=user.pk) | Q(leads__pk__in=scoped_lead_ids) | Q(activities__author_id=user.pk),
    ).distinct()


def scope_activities_for_manager(
    queryset: QuerySet[Activity],
    user: Any,
) -> QuerySet[Activity]:
    """Limit activities to scoped clients or ones authored by the user.

    Args:
        queryset: base Activity queryset.
        user: authenticated staff user.

    Returns:
        Filtered Activity queryset.
    """
    from accounts.roles import staff_sees_all_leads

    if staff_sees_all_leads(user):
        return queryset
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return queryset.none()

    client_ids = scope_clients_for_manager(Client.objects.all(), user).values("pk")
    return queryset.filter(
        Q(client_id__in=client_ids) | Q(author_id=user.pk),
    ).distinct()


def scope_emails_for_manager(
    queryset: QuerySet[EmailMessage],
    user: Any,
) -> QuerySet[EmailMessage]:
    """Limit email rows to clients visible to the manager.

    Args:
        queryset: base EmailMessage queryset.
        user: authenticated staff user.

    Returns:
        Filtered EmailMessage queryset.
    """
    from accounts.roles import staff_sees_all_leads

    if staff_sees_all_leads(user):
        return queryset
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return queryset.none()

    client_ids = scope_clients_for_manager(Client.objects.all(), user).values("pk")
    return queryset.filter(client_id__in=client_ids)
