"""Company card helpers: auto-link from Client, colleagues, merge."""

from __future__ import annotations

from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from crm.models import Client, Company, CompanyMember


def ensure_company_ref(client: Client) -> Company | None:
    """Attach a Company row for a client with a company label.

    Текстовое ``company`` / ``company_key`` остаётся ключом маршрутизации;
    ``company_ref`` — карточка юрлица (коллеги, ИНН, объединение).

    Args:
        client: saved Client (needs pk).

    Returns:
        Linked Company, or None when the label is empty.
    """
    if not client.pk:
        return None
    key = (client.company_key or "").strip()
    if not key:
        return cast("Company | None", client.company_ref)
    org = cast("Company | None", Company.objects.filter(company_key=key).first())
    if org is None:
        try:
            org = Company.objects.create(name=(client.company or "").strip() or key)
        except IntegrityError:
            org = cast("Company | None", Company.objects.filter(company_key=key).first())
    if org is None:
        return cast("Company | None", client.company_ref)
    if client.company_ref_id != org.pk:
        Client.objects.filter(pk=client.pk).update(company_ref=org)
        client.company_ref_id = org.pk
        client.company_ref = org
    _ensure_member(org, client)
    return org


def _ensure_member(org: Company, client: Client) -> None:
    """Create a CompanyMember row if this contact is not listed yet."""
    exists = CompanyMember.objects.filter(company=org, client=client).exists()
    if exists:
        return
    CompanyMember.objects.create(
        company=org,
        client=client,
        account=client.account,
    )


def colleague_clients(client: Client) -> QuerySet[Client]:
    """Other active cards of the same company (FK or normalized key)."""
    qs = Client.objects.filter(is_active=True).exclude(pk=client.pk)
    if client.company_ref_id:
        return qs.filter(company_ref_id=client.company_ref_id)
    key = (client.company_key or "").strip()
    if not key:
        return qs.none()
    return qs.filter(company_key=key)


def similar_clients(client: Client) -> QuerySet[Client]:
    """Likely duplicates: same company or same phone, different email."""
    qs = Client.objects.filter(is_active=True).exclude(pk=client.pk)
    clauses = Q()
    key = (client.company_key or "").strip()
    if key:
        clauses |= Q(company_key=key)
    if client.company_ref_id:
        clauses |= Q(company_ref_id=client.company_ref_id)
    digits = (client.phone_digits or "").strip()
    if len(digits) >= 10:
        clauses |= Q(phone_digits=digits)
    if not clauses:
        return qs.none()
    return qs.filter(clauses).distinct()


def merge_companies(
    target: Company,
    sources: list[Company],
    *,
    actor: Any = None,
) -> dict[str, int]:
    """Move clients/members from ``sources`` onto ``target``, then delete sources.

    Args:
        target: surviving company card.
        sources: duplicates to absorb.
        actor: unused (reserved for timeline); merge is structural.

    Returns:
        Counts of moved clients and members.
    """
    del actor
    moved = {"clients": 0, "members": 0}
    with transaction.atomic():
        for source in sources:
            if source.pk == target.pk:
                continue
            moved["clients"] += Client.objects.filter(company_ref=source).update(
                company_ref=target,
            )
            moved["members"] += CompanyMember.objects.filter(company=source).update(
                company=target,
            )
            source.delete()
        seen: set[tuple[int | None, int | None]] = set()
        for member in CompanyMember.objects.filter(company=target).order_by("pk"):
            key = (member.client_id, member.account_id)
            if key in seen:
                member.delete()
                continue
            seen.add(key)
    return moved
