"""Quote lifecycle helpers: issue, copy, order, spec import, sibling warning."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from cabinet.models import Order, OrderItem, OrderStatus, SpecList
from crm.models import Client, Quote, QuoteItem, QuoteStatus
from leads.models import Lead


def sibling_open_quotes(client: Client) -> list[Quote]:
    """Open КП of colleagues at the same company (not this contact)."""
    from crm.company import colleague_clients

    colleague_ids = list(colleague_clients(client).values_list("pk", flat=True))
    if not colleague_ids:
        return []
    return list(
        Quote.objects.filter(
            client_id__in=colleague_ids,
            status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT),
        )
        .select_related("client", "created_by")
        .order_by("-created_at")[:8],
    )


def finalize_quote_status(quote: Quote, *, actor: Any = None) -> dict[str, Any]:
    """Stamp first SENT, issue PDF, close source lead; clear sent_at if unsent.

    Idempotent on re-save of an already issued quote.

    Args:
        quote: saved Quote with the desired ``status``.
        actor: staff user for lead close / notify.

    Returns:
        Flags for Admin messages: ``issued``, ``lead_closed``, ``lead_error``,
        ``pdf_error``.
    """
    result: dict[str, Any] = {
        "issued": False,
        "lead_closed": None,
        "lead_error": None,
        "pdf_error": None,
    }
    if quote.status == QuoteStatus.SENT:
        if quote.sent_at is not None:
            return result
        quote.sent_at = timezone.now()
        quote.save(update_fields=["sent_at", "updated_at"])
        result["issued"] = True
        from crm.quote_docs import ensure_quote_pdf_document, notify_quote_issued

        try:
            document = ensure_quote_pdf_document(quote)
        except Exception as exc:  # PDF must not block SENT
            result["pdf_error"] = f"{type(exc).__name__}"
            document = None
        client = cast(Client, quote.client)
        if document is not None and client.email:
            notify_quote_issued(quote, author=actor, document=document)
        lead = cast("Lead | None", quote.lead)
        if lead is not None and lead.status != Lead.LeadStatus.DONE:
            from leads.services import set_lead_status

            updated, error = set_lead_status(
                lead,
                status=Lead.LeadStatus.DONE,
                actor=actor,
            )
            if error:
                result["lead_error"] = error
            else:
                result["lead_closed"] = updated.pk
        return result
    if quote.sent_at is not None:
        quote.sent_at = None
        quote.save(update_fields=["sent_at", "updated_at"])
    return result


def duplicate_quote(quote: Quote, *, author: Any) -> Quote:
    """Copy КП into a new draft (new number, +14 days validity)."""
    with transaction.atomic():
        copy = Quote.objects.create(
            client=cast(Client, quote.client),
            lead=cast("Lead | None", quote.lead),
            created_by=author,
            status=QuoteStatus.DRAFT,
            comment=quote.comment,
            vat_rate=quote.vat_rate,
            valid_until=timezone.localdate() + timedelta(days=14),
        )
        items = [
            QuoteItem(
                quote=copy,
                sku=item.sku,
                sku_code=item.sku_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                sort_order=item.sort_order,
            )
            for item in quote.items.all()
        ]
        if items:
            QuoteItem.objects.bulk_create(items)
    return copy


def create_order_from_quote(quote: Quote) -> tuple[Order, bool]:
    """Create (or reuse) a non-cancelled Order from quote lines.

    Returns:
        ``(order, created)``.
    """
    existing = quote.orders.exclude(status=OrderStatus.CANCELLED).order_by("pk").first()
    if existing is not None:
        return existing, False
    base = f"З-{quote.number or quote.pk}"
    number = base
    suffix = 2
    while Order.objects.filter(client_id=quote.client_id, number=number).exists():
        number = f"{base}-{suffix}"
        suffix += 1
    with transaction.atomic():
        order = Order.objects.create(
            client=cast(Client, quote.client),
            quote=quote,
            number=number,
            status=OrderStatus.ACCEPTED,
            comment=quote.comment,
        )
        items = [
            OrderItem(
                order=order,
                sku=item.sku,
                sku_code=item.sku_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                sort_order=item.sort_order,
            )
            for item in quote.items.all()
        ]
        if items:
            OrderItem.objects.bulk_create(items)
    return order, True


def create_quote_from_spec(spec: SpecList, *, author: Any) -> Quote | None:
    """Draft Quote from a cabinet spec list (client's ЛК account).

    Returns:
        New quote, or None when the spec account has no CRM card.
    """
    account = spec.account
    try:
        client = account.crm_client
    except Client.DoesNotExist:
        return None
    with transaction.atomic():
        quote = Quote.objects.create(
            client=client,
            created_by=author,
            status=QuoteStatus.DRAFT,
            comment=spec.note or spec.name,
        )
        items = [
            QuoteItem(
                quote=quote,
                sku=row.sku,
                sku_code=row.sku_code,
                quantity=row.quantity,
                sort_order=row.position,
            )
            for row in spec.items.all()
        ]
        if items:
            QuoteItem.objects.bulk_create(items)
    return quote
