"""CRM services: find/create Client from Lead, queue outbound email."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.db.models import Q, QuerySet

from config.logging_utils import setup_logger
from crm.models import (
    Activity,
    ActivityType,
    Client,
    EmailDirection,
    EmailMessage,
    EmailStatus,
    EmailTemplate,
    Quote,
    QuoteItem,
    QuoteStatus,
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

    The whole read/create/merge sequence runs in one transaction and the
    returned row is re-locked with ``select_for_update()`` so concurrent
    leads with the same email cannot overwrite each other's merge.

    Args:
        lead: saved Lead instance.

    Returns:
        Client linked (or to be linked) to this lead.
    """
    email = normalize_client_email(lead.email)
    defaults = {
        "name": normalize_client_name(lead.name) or email,
        "phone": lead.phone or "",
        "company": normalize_client_company(lead.company),
    }
    with transaction.atomic():
        client, created = Client.objects.get_or_create(
            email=email,
            defaults=defaults,
        )
        # Re-fetch locked so a concurrent lead with the same email waits for
        # this transaction before it reads/merges the same card.
        client = Client.objects.select_for_update().get(pk=client.pk)
        if not created:
            return _merge_lead_contact_into_client(client, lead)
        return client


def get_or_create_client_by_email(
    *,
    email: str,
    name: str = "",
    phone: str = "",
    company: str = "",
) -> Client:
    """Find or create the CRM card by email (used by client auth linking).

    Same normalization as the lead path; fills only empty fields.
    """
    email = normalize_client_email(email)
    with transaction.atomic():
        client, created = Client.objects.get_or_create(
            email=email,
            defaults={
                "name": normalize_client_name(name) or email,
                "phone": (phone or "").strip(),
                "company": normalize_client_company(company),
            },
        )
        client = Client.objects.select_for_update().get(pk=client.pk)
        if not created:
            updated = False
            if not client.phone and phone:
                client.phone = phone.strip()
                updated = True
            if not client.company and company:
                client.company = normalize_client_company(company)
                updated = True
            if updated:
                client.save()
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


def _personal_smtp_mailbox(user: Any) -> Any | None:
    """Author's StaffMailbox ready for SMTP, or None → общий env-ящик.

    Ящик считается готовым к отправке, когда он включён и заполнены
    адрес, пароль приложения и SMTP-сервер.
    """
    if user is None:
        return None
    mailbox = getattr(user, "mailbox", None)
    if (
        mailbox is not None
        and mailbox.is_enabled
        and (mailbox.smtp_host or "").strip()
        and (mailbox.imap_user or "").strip()
        and (mailbox.imap_password or "")
    ):
        return mailbox
    return None


def create_outbound_email(
    *,
    client: Client,
    subject: str,
    body: str,
    to_email: str | None = None,
    lead: Lead | None = None,
    author: AbstractBaseUser | None = None,
    reply_to_email: str | None = None,
    send_now: bool = True,
    attachments: Iterable[tuple[str, str, bytes]] | None = None,
) -> EmailMessage:
    """Create an outbound EmailMessage and optionally queue send.

    Args:
        client: CRM client.
        subject: email subject.
        body: plain-text body.
        to_email: override recipient (default client.email).
        lead: optional related Lead.
        author: staff User who composed the message.
        reply_to_email: optional Reply-To header (manager mailbox).
        send_now: enqueue Celery send after commit.
        attachments: optional ``(filename, content_type, bytes)`` rows stored
            as ``EmailAttachment`` (private media) and sent with the email.

    Returns:
        Created EmailMessage (status DRAFT or QUEUED).
    """
    from django.core.files.base import ContentFile

    from crm.models import EmailAttachment

    from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "webmaster@localhost"
    created_by = author if author is not None and author.is_authenticated else None
    mailbox = _personal_smtp_mailbox(created_by)
    if mailbox is not None:
        from_addr = (mailbox.imap_user or "").strip() or from_addr
    reply_to = (reply_to_email or "").strip()
    msg = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED if send_now else EmailStatus.DRAFT,
        to_email=(to_email or client.email).strip(),
        from_email=from_addr,
        reply_to_email=reply_to,
        mailbox=mailbox,
        subject=subject.strip(),
        body=body.strip(),
        created_by=created_by,  # type: ignore[misc]
    )
    for filename, content_type, content in attachments or ():
        EmailAttachment.objects.create(
            email=msg,
            filename=filename,
            content_type=content_type,
            size=len(content),
            file=ContentFile(content, name=filename),
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


def create_lead_reply_email(
    *,
    lead: Lead,
    subject: str,
    body: str,
    to_email: str | None = None,
    author: AbstractBaseUser | None = None,
    reply_to_email: str | None = None,
    send_now: bool = True,
) -> EmailMessage:
    """Queue a KP reply to a lead: CRM client card, Reply-To manager, footer hint.

    Args:
        lead: RFQ / consultation lead being answered.
        subject: email subject.
        body: manager-edited plain text (footer appended on send).
        to_email: override recipient (default lead.email).
        author: staff user who composed the reply.
        reply_to_email: manager mailbox for client replies.
        send_now: enqueue Celery send after commit.

    Returns:
        Created EmailMessage linked to the lead and CRM client.
    """
    from crm.manager_signatures import assemble_lead_reply_body

    client = get_or_create_client_from_lead(lead)
    reply_to = (reply_to_email or "").strip()
    full_body = assemble_lead_reply_body(body, reply_to)
    return create_outbound_email(
        client=client,
        lead=lead,
        subject=subject,
        body=full_body,
        to_email=to_email,
        author=author,
        reply_to_email=reply_to,
        send_now=send_now,
    )


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
    return queryset.filter(
        Q(client_id__in=client_ids) | Q(mailbox__user=user),
    ).distinct()


def get_active_email_template(template_id: str | int | None) -> EmailTemplate | None:
    """Active EmailTemplate picked in a compose form (``?template=<pk>``).

    Args:
        template_id: raw GET/POST value (str/int/None).

    Returns:
        EmailTemplate instance or None when missing/inactive/malformed.
    """
    raw = str(template_id or "").strip()
    if not raw.isdigit():
        return None
    return EmailTemplate.objects.filter(pk=int(raw), is_active=True).first()


def email_template_context_for_client(client: Client) -> dict[str, str]:
    """Placeholder values for template substitution from a Client card."""
    return {
        "имя": client.name or "",
        "компания": client.company or "",
        "почта": client.email or "",
        "телефон": client.phone or "",
    }


def email_template_context_for_lead(lead: Lead) -> dict[str, str]:
    """Placeholder values for template substitution from a Lead contact."""
    return {
        "имя": lead.name or "",
        "компания": lead.company or "",
        "почта": lead.email or "",
        "телефон": lead.phone or "",
    }


def render_email_template(
    template: EmailTemplate,
    *,
    context: dict[str, str],
) -> tuple[str, str]:
    """Substitute ``{имя}``/``{компания}``/``{почта}``/``{телефон}`` placeholders.

    Plain ``str.replace`` — unknown placeholders and stray braces are kept
    as-is (no ``format()`` crash on user-edited text).

    Args:
        template: EmailTemplate with subject/body.
        context: placeholder → value mapping (see ``email_template_context_*``).

    Returns:
        ``(subject, body)`` with placeholders substituted.
    """
    subject, body = template.subject, template.body
    for key, value in context.items():
        token = "{" + key + "}"
        subject = subject.replace(token, value)
        body = body.replace(token, value)
    return subject.strip(), body.strip()


def create_quote_from_lead(lead: Lead, *, author: Any) -> tuple[Quote, bool]:
    """Create a draft Quote prefilled from the lead's items.

    Кнопка «Создать КП» на карточке заявки. Если у заявки уже есть
    открытое КП (черновик/выдано) — возвращает его, дубли не создаются.
    Без карточки клиента — привязывает по email через ``link_lead_to_client``.

    Args:
        lead: исходная заявка.
        author: менеджер, выписывающий КП.

    Returns:
        ``(quote, created)`` — ``created`` False при переиспользовании
        открытого КП.
    """
    open_quote = lead.quotes.filter(status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT)).order_by("-created_at").first()
    if open_quote is not None:
        return open_quote, False
    client = link_lead_to_client(lead)
    with transaction.atomic():
        quote = Quote.objects.create(
            client=client,
            lead=lead,
            created_by=author,
            status=QuoteStatus.DRAFT,
        )
        items = [
            QuoteItem(
                quote=quote,
                sku=item.sku,
                sku_code=item.sku_code,
                quantity=item.quantity,
                sort_order=item.sort_order,
            )
            for item in lead.items.all()
        ]
        if items:
            QuoteItem.objects.bulk_create(items)
    return quote, True


def merge_clients(target: Client, sources: list[Client], *, actor: Any = None) -> dict[str, int]:
    """Merge duplicate client cards into ``target`` (same company, diff emails).

    Все связи переносятся на целевую карточку: заявки, активности, письма,
    КП, документы, заказы, RMA, диалоги поддержки, членства в компаниях.
    Пустые поля цели заполняются из источников; привязка аккаунта ЛК
    сохраняется (у цели приоритет, иначе берётся первый найденный).
    Исходные карточки деактивируются (``is_active=False``), не удаляются —
    email уникален, а история перенесена.

    Args:
        target: целевая карточка (остаётся).
        sources: карточки-дубли (минимум одна).
        actor: staff-пользователь для записи в таймлайн.

    Returns:
        Счётчики перенесённых связей по типам.
    """
    from cabinet.models import Order, RmaCase
    from supportchat.models import Conversation

    moved = {
        "leads": 0,
        "activities": 0,
        "emails": 0,
        "quotes": 0,
        "documents": 0,
        "orders": 0,
        "rma_cases": 0,
        "conversations": 0,
    }
    emails_log: list[str] = []
    with transaction.atomic():
        for source in sources:
            if source.pk == target.pk:
                continue
            moved["leads"] += source.leads.update(client=target)
            moved["activities"] += source.activities.update(client=target)
            moved["emails"] += source.emails.update(client=target)
            moved["quotes"] += source.quotes.update(client=target)
            moved["documents"] += source.documents.update(client=target)
            moved["orders"] += Order.objects.filter(client=source).update(client=target)
            moved["rma_cases"] += RmaCase.objects.filter(client=source).update(client=target)
            moved["conversations"] += Conversation.objects.filter(client=source).update(
                client=target,
            )
            source.company_memberships.update(client=target)
            if source.account_id and target.account_id is None:
                target.account_id = source.account_id
                source.account = None
                source.save(update_fields=["account", "updated_at"])
            # Fill empty target fields from the richest source.
            for field in ("name", "phone", "company"):
                if not getattr(target, field) and getattr(source, field):
                    setattr(target, field, getattr(source, field))
            if source.company_ref_id and target.company_ref_id is None:
                target.company_ref_id = source.company_ref_id
            if source.assignee_id and target.assignee_id is None:
                target.assignee_id = source.assignee_id
            if source.notes:
                target.notes = f"{target.notes}\n[{source.email}] {source.notes}".strip()
            emails_log.append(source.email)
            source.is_active = False
            source.save(update_fields=["is_active", "updated_at"])
        target.save()
        Activity.objects.create(
            client=target,
            activity_type=ActivityType.OTHER,
            subject="Объединение карточек",
            body=f"Перенесены связи с карточек: {', '.join(emails_log)}",
            author=actor if actor is not None and actor.is_authenticated else None,  # type: ignore[misc]
        )
    return moved
