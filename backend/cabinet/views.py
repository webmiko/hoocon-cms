"""Client cabinet API views: ``/api/auth/*`` + ``/api/account/*``.

Auth: session cookie (``cabinet.auth.login_client``) — no JWT, no staff
User. Owner-scope: every object resolves through ``client.account`` —
foreign ids → 404 (project policy, §3 of the cabinet plan).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import ClientAccount
from cabinet.auth import IsClientAccount, load_client_account, login_client, logout_client
from cabinet.authentication import ClientSessionAuthentication
from cabinet.models import SpecList
from cabinet.serializers import (
    DocumentSerializer,
    LoginSerializer,
    OrderSerializer,
    OtpResendSerializer,
    OtpStartSerializer,
    OtpVerifySerializer,
    ProfilePatchSerializer,
    QuoteSerializer,
    RegisterSerializer,
    RmaCaseCreateSerializer,
    RmaCaseSerializer,
    SpecListSerializer,
    SpecListWriteSerializer,
)
from cabinet.services import (
    ClientAuthError,
    ClientRateLimitError,
    authenticate_password,
    check_honeypot,
    link_client_account,
    resend_client_otp,
    start_client_otp,
    start_client_registration,
    verify_client_otp,
)
from config.pagination import DefaultPagination
from crm.models import Client, QuoteStatus
from leads.lifecycle import on_lead_created
from leads.models import Lead

logger = logging.getLogger(__name__)

_REPEAT_WINDOW_SECONDS = 300


def _session_account(request: Request) -> ClientAccount:
    """The authenticated client account (IsClientAccount guarantees it)."""
    user = request.user
    account = user if isinstance(user, ClientAccount) else load_client_account(request)
    if account is None:
        raise Http404
    return account


def _client_for(request: Request) -> Client:
    """Resolve the CRM card linked to the verified session account.

    Read-only on the hot path; linking (by proven email) happens at
    verification and only re-runs when staff unlinked the card.
    """
    account = _session_account(request)
    client = Client.objects.filter(account=account).first()
    return client if client is not None else link_client_account(account)


def _auth_error(exc: ClientAuthError) -> Response:
    """Uniform error shape for /api/auth/*; 429 for send quotas."""
    code = status.HTTP_429_TOO_MANY_REQUESTS if isinstance(exc, ClientRateLimitError) else status.HTTP_400_BAD_REQUEST
    return Response({"detail": str(exc)}, status=code)


def _account_payload(account: ClientAccount) -> dict[str, Any]:
    """Profile + feature flags for the SPA shell."""
    modes = []
    if account.has_usable_password():
        modes.append("password")
    modes.append("otp_email")
    return {
        "email": account.email,
        "name": account.name,
        "phone": account.phone,
        "auth_modes": modes,
        "features": {
            "quotes": True,
            "orders": True,
            "specs": True,
            "documents": True,
            "conversations": True,
            "rma": True,
        },
    }


# ---------------------------------------------------------------------------
# Auth endpoints (/api/auth/*)
# ---------------------------------------------------------------------------


class _CabinetGatedView(APIView):
    """404 the whole cabinet API while the feature flag is off.

    ``SiteSettings.cabinet_enabled=False`` глушит весь контур
    (/api/auth/* + /api/account/*) одним ответом 404 — кабинет
    не подхватывается, пока его не включат в Admin → Интеграции.
    """

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Run the feature-flag check inside DRF's exception boundary."""
        from sitesettings.models import SiteSettings

        if not SiteSettings.load().cabinet_enabled:
            raise NotFound()
        super().initial(request, *args, **kwargs)


class _AuthView(_CabinetGatedView):
    """``/api/auth/*``: CSRF even for anonymous visitors, JSON bodies only.

    DRF skips CSRF for unauthenticated requests, which allowed login CSRF:
    a foreign page could sign the victim into the attacker's cabinet.
    """

    parser_classes = (JSONParser,)

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if request.method not in SAFE_METHODS:
            SessionAuthentication().enforce_csrf(request)


class RegisterView(_AuthView):
    """POST /api/auth/register/ — mode A step 1: email a confirmation code.

    Same response as ``otp/start``; the account is created by
    ``otp/verify`` once the code proves the email belongs to the visitor.
    """

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            check_honeypot(request, data.get("form_start_ts"), data.get("website", ""))
            result = start_client_registration(
                request._request,  # noqa: SLF001 — DRF wraps HttpRequest
                email=data["email"],
                password=data["password"],
                name=data.get("name", ""),
                phone=data.get("phone", ""),
                pdn_consent=data["pdn_consent"],
            )
        except ClientAuthError as exc:
            # Honeypot/validation errors share one shape — no detail leaks.
            return _auth_error(exc)
        return Response(result, status=status.HTTP_202_ACCEPTED)


class LoginView(_AuthView):
    """POST /api/auth/login/ — mode A password check."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            account = authenticate_password(
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
            )
        except ClientAuthError as exc:
            return _auth_error(exc)
        login_client(request._request, account)  # noqa: SLF001
        return Response(_account_payload(account))


class OtpStartView(_AuthView):
    """POST /api/auth/otp/start/ — mode B: send a fresh 6-digit code."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = OtpStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            check_honeypot(request, data.get("form_start_ts"), data.get("website", ""))
            result = start_client_otp(
                request._request,  # noqa: SLF001
                data["email"],
                pdn_consent=data["pdn_consent"],
            )
        except ClientAuthError as exc:
            return _auth_error(exc)
        return Response(result)


class OtpVerifyView(_AuthView):
    """POST /api/auth/otp/verify/ — mode B: verify the code → session."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            account = verify_client_otp(
                challenge_id=serializer.validated_data["challenge_id"],
                code=serializer.validated_data["code"],
            )
        except ClientAuthError as exc:
            return _auth_error(exc)
        login_client(request._request, account)  # noqa: SLF001
        return Response(_account_payload(account))


class OtpResendView(_AuthView):
    """POST /api/auth/otp/resend/ — cooldown-gated resend."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = OtpResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = resend_client_otp(
                request._request,  # noqa: SLF001
                serializer.validated_data["challenge_id"],
            )
        except ClientAuthError as exc:
            return _auth_error(exc)
        return Response(result)


class LogoutView(_AuthView):
    """POST /api/auth/logout/ — drop the client session."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        logout_client(request._request)  # noqa: SLF001
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthMeView(_CabinetGatedView):
    """GET /api/auth/me/ — current session account or 401."""

    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        account = load_client_account(request)
        if account is None:
            return Response({"detail": "Не авторизован."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_account_payload(account))


# ---------------------------------------------------------------------------
# Cabinet endpoints (/api/account/*) — owner scope via client.account
# ---------------------------------------------------------------------------


class ClientApiView(_CabinetGatedView):
    """Base for /api/account/* endpoints: session auth + CSRF + owner scope.

    ``ClientSessionAuthentication`` resolves the ``ClientAccount`` into
    ``request.user`` and enforces CSRF on mutating methods — the same
    rule DRF applies to staff sessions.
    """

    authentication_classes = (ClientSessionAuthentication,)
    permission_classes = (IsClientAccount,)


class AccountMeView(ClientApiView):
    """GET/PATCH /api/account/me/ — cabinet profile."""

    def get(self, request: Request) -> Response:
        account = _session_account(request)
        return Response(_account_payload(account))  # type: ignore[arg-type]

    def patch(self, request: Request) -> Response:
        account = _session_account(request)
        serializer = ProfilePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        changed = False
        if "name" in data:
            account.name = data["name"].strip()  # type: ignore[union-attr]
            changed = True
        if "phone" in data:
            account.phone = data["phone"].strip()  # type: ignore[union-attr]
            changed = True
        if changed:
            account.save(update_fields=["name", "phone", "updated_at"])  # type: ignore[union-attr]
            _client_for(request)  # keep card linked
        return Response(_account_payload(account))  # type: ignore[arg-type]


class AccountSummaryView(ClientApiView):
    """GET /api/account/summary/ — dashboard counters."""

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        from supportchat.models import ConversationStatus

        return Response(
            {
                "active_leads": _scoped_leads(client).exclude(status=Lead.LeadStatus.DONE).count(),
                "quotes_pending": client.quotes.filter(status=QuoteStatus.SENT).count(),
                "orders_in_work": client.orders.exclude(status__in=("done", "cancelled")).count(),
                "unread_conversations": _scoped_conversations(client).filter(status=ConversationStatus.OPEN).count(),
            }
        )


def _scoped_leads(client: Client) -> QuerySet[Lead]:
    """Leads proven to belong to this client (``contact_verified``).

    Anyone can type a foreign email into the public form. Taking the lead
    into work proves nothing about the sender, so only an explicit
    confirmation (cabinet, manager link, sent quote) surfaces it.
    """
    return client.leads.filter(contact_verified=True).prefetch_related("items__sku").order_by("-created_at")


def _scoped_conversations(client: Client) -> QuerySet[Any]:
    """Chats proven to belong to this client (``contact_verified``).

    ``contact_email`` in the widget is typed by the visitor; a manager reply
    does not prove the visitor owns that mailbox.
    """
    from supportchat.models import Conversation

    return Conversation.objects.filter(client=client, contact_verified=True)


def _lead_payload(lead: Lead) -> dict[str, Any]:
    return {
        "id": lead.pk,
        "type": lead.lead_type,
        "type_label": lead.get_lead_type_display(),
        "status": lead.status,
        "status_label": lead.get_status_display(),
        "company": lead.company,
        "message": lead.message,
        "created_at": lead.created_at,
        "items": [
            {
                "id": item.pk,
                "sku_code": item.sku_code or (item.sku.sku_code if item.sku else ""),
                "sku": item.sku_id,
                "name": (item.sku.name if item.sku else "") or item.sku_code,
                "quantity": item.quantity,
            }
            for item in lead.items.all()
        ],
    }


class AccountLeadsView(ClientApiView):
    """GET /api/account/leads/ — own leads only."""

    pagination_class = DefaultPagination

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        leads = _scoped_leads(client)
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            leads = leads.filter(status=status_filter)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(leads, request)
        return paginator.get_paginated_response([_lead_payload(lead) for lead in page] if page else [])


class AccountLeadDetailView(ClientApiView):
    """GET /api/account/leads/<id>/ — own lead detail (404 on foreign)."""

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        lead = get_object_or_404(_scoped_leads(client), pk=pk)
        payload = _lead_payload(lead)
        quotes = lead.quotes.exclude(status=QuoteStatus.DRAFT).prefetch_related("items").order_by("-created_at")
        payload["quotes"] = QuoteSerializer(quotes, many=True).data
        return Response(payload)


class AccountLeadRepeatView(ClientApiView):
    """POST /api/account/leads/<id>/repeat/ — clone positions into a new RFQ.

    Idempotent within a 5-minute window (§9): a repeat of the same source
    lead returns the already-created copy instead of spawning duplicates.
    """

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_repeat"

    def post(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        source = get_object_or_404(_scoped_leads(client), pk=pk)
        repeat_message = f"Повтор заявки #{source.pk}"
        recent = (
            Lead.objects.filter(
                client=client,
                created_at__gte=timezone.now() - timedelta(seconds=_REPEAT_WINDOW_SECONDS),
                message=repeat_message,
                lead_type=Lead.LeadType.RFQ,
            )
            .order_by("-created_at")
            .first()
        )
        if recent is not None:
            return Response(_lead_payload(recent), status=status.HTTP_200_OK)
        with transaction.atomic():
            lead = Lead.objects.create(
                lead_type=Lead.LeadType.RFQ,
                name=client.name or client.email,
                email=client.email,
                phone=client.phone,
                company=client.company,
                client=client,
                contact_verified=True,
                message=repeat_message,
            )
            for item in source.items.all():
                lead.items.create(
                    sku=item.sku,
                    sku_code=item.sku_code,
                    quantity=item.quantity,
                    sort_order=item.sort_order,
                )
            on_lead_created(lead)
        return Response(_lead_payload(lead), status=status.HTTP_201_CREATED)


class AccountSpecsView(ClientApiView):
    """GET/POST /api/account/specs/ — spec templates CRUD (owner scope)."""

    def get(self, request: Request) -> Response:
        account = _session_account(request)
        specs = SpecList.objects.filter(account=account).prefetch_related("items__sku").order_by("-updated_at")
        return Response(SpecListSerializer(specs, many=True).data)

    def post(self, request: Request) -> Response:
        account = _session_account(request)
        serializer = SpecListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spec = _save_spec(account, serializer.validated_data)  # type: ignore[arg-type]
        return Response(SpecListSerializer(spec).data, status=status.HTTP_201_CREATED)


class AccountSpecDetailView(ClientApiView):
    """GET/PATCH/DELETE /api/account/specs/<id>/ — owner scope."""

    def get(self, request: Request, pk: int) -> Response:
        account = _session_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account).prefetch_related("items__sku"), pk=pk)
        return Response(SpecListSerializer(spec).data)

    def patch(self, request: Request, pk: int) -> Response:
        account = _session_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account), pk=pk)
        serializer = SpecListWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        spec = _save_spec(account, serializer.validated_data, spec=spec)  # type: ignore[arg-type]
        return Response(SpecListSerializer(spec).data)

    def delete(self, request: Request, pk: int) -> Response:
        account = _session_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account), pk=pk)
        spec.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountSpecToLeadView(ClientApiView):
    """POST /api/account/specs/<id>/to_lead/ — draft an RFQ from a spec."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_repeat"

    def post(self, request: Request, pk: int) -> Response:
        account = _session_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account).prefetch_related("items"), pk=pk)
        client = _client_for(request)
        with transaction.atomic():
            lead = Lead.objects.create(
                lead_type=Lead.LeadType.RFQ,
                name=client.name or client.email,
                email=client.email,
                phone=client.phone,
                company=client.company,
                client=client,
                contact_verified=True,
                message=f"Заявка из спецификации «{spec.name}»",
            )
            for item in spec.items.all():
                lead.items.create(
                    sku=item.sku,
                    sku_code=item.sku_code,
                    quantity=item.quantity,
                    sort_order=item.position,
                )
            on_lead_created(lead)
        return Response(_lead_payload(lead), status=status.HTTP_201_CREATED)


def _save_spec(account: ClientAccount, data: dict[str, Any], spec: SpecList | None = None) -> SpecList:
    """Create or update a SpecList with its items (items list replaces)."""
    from catalog.models import SKU

    with transaction.atomic():
        if spec is None:
            spec = SpecList.objects.create(
                account=account,
                name=data["name"].strip(),
                note=data.get("note", "").strip(),
            )
        else:
            if "name" in data:
                spec.name = data["name"].strip()
            if "note" in data:
                spec.note = data["note"].strip()
            spec.save()
        if "items" in data:
            spec.items.all().delete()
            for idx, raw in enumerate(data["items"]):
                code = (raw.get("sku_code") or "").strip()
                sku = raw.get("sku")
                if sku is None and code:
                    sku = SKU.objects.filter(is_published=True, sku_code__iexact=code).first()
                position = raw.get("position")
                spec.items.create(
                    sku=sku,
                    sku_code=code or (sku.sku_code if sku else ""),
                    quantity=raw.get("quantity") or 1,
                    position=idx if position is None else position,
                )
    return spec


class AccountQuotesView(ClientApiView):
    """GET /api/account/quotes/ — issued quotes (drafts hidden)."""

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        quotes = client.quotes.exclude(status=QuoteStatus.DRAFT).prefetch_related("items").order_by("-created_at")
        return Response(QuoteSerializer(quotes, many=True).data)


class AccountQuoteDetailView(ClientApiView):
    """GET /api/account/quotes/<id>/ — own quote detail."""

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        quote = get_object_or_404(
            client.quotes.exclude(status=QuoteStatus.DRAFT).prefetch_related("items__sku"),
            pk=pk,
        )
        return Response(QuoteSerializer(quote).data)


class AccountQuotePdfView(ClientApiView):
    """GET /api/account/quotes/<id>/pdf/ — generated PDF (ЛК-3)."""

    def get(self, request: Request, pk: int) -> FileResponse:
        client = _client_for(request)
        quote = get_object_or_404(client.quotes.exclude(status=QuoteStatus.DRAFT), pk=pk)
        from crm.quote_pdf import render_quote_pdf

        pdf = render_quote_pdf(quote)
        return FileResponse(pdf, content_type="application/pdf", filename=f"{quote.number}.pdf")


class AccountDocumentsView(ClientApiView):
    """GET /api/account/documents/ — all files of the client card."""

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        docs = client.documents.order_by("-created_at")
        return Response(DocumentSerializer(docs, many=True).data)


class AccountDocumentDownloadView(ClientApiView):
    """GET /api/account/documents/<id>/download/ — owner-only private file."""

    def get(self, request: Request, pk: int) -> FileResponse:
        client = _client_for(request)
        doc = get_object_or_404(client.documents, pk=pk)
        return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.title)


# Sum of document sizes one archive may hold; bigger sets are downloaded
# one by one (the archive is spooled to disk, not kept in RAM).
DOCUMENTS_ZIP_MAX_BYTES = 200 * 1024 * 1024
_ZIP_SPOOL_BYTES = 8 * 1024 * 1024


class AccountDocumentsZipView(ClientApiView):
    """GET /api/account/documents/zip/ — все документы клиента одним ZIP (ЛК-8).

    Files come from private media only; names are sanitized against
    path traversal and de-duplicated inside the archive. The archive is
    built in a spooled temp file with a total size cap and its own throttle.
    """

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_zip"

    def get(self, request: Request) -> FileResponse | Response:
        import shutil
        import tempfile
        import zipfile

        from catalog.validators import sanitize_upload_filename

        client = _client_for(request)
        docs = [doc for doc in client.documents.order_by("kind", "created_at") if doc.file]
        total = 0
        for doc in docs:
            try:
                total += doc.file.size
            except (FileNotFoundError, OSError):
                continue
        if total > DOCUMENTS_ZIP_MAX_BYTES:
            return Response(
                {"detail": "Документов слишком много для одного архива — скачайте их по отдельности."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        buf = tempfile.SpooledTemporaryFile(max_size=_ZIP_SPOOL_BYTES)  # noqa: SIM115
        used_names: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in docs:
                base = sanitize_upload_filename(doc.title or f"document-{doc.pk}")
                name = base
                n = 2
                while name in used_names:
                    stem, dot, ext = base.rpartition(".")
                    name = f"{stem}-{n}.{ext}" if dot else f"{base}-{n}"
                    n += 1
                try:
                    with doc.file.open("rb") as fh, zf.open(name, "w") as out:
                        shutil.copyfileobj(fh, out, 1024 * 1024)
                except (FileNotFoundError, OSError):
                    logger.warning("account_zip_missing_file document_id=%s", doc.pk)
                    continue
                used_names.add(name)
        buf.seek(0)
        filename = f"hoocon-docs-{client.pk}.zip"
        return FileResponse(buf, as_attachment=True, filename=filename)


class AccountOrdersView(ClientApiView):
    """GET /api/account/orders/ — own orders (ЛК-6)."""

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        orders = client.orders.prefetch_related("items__sku").order_by("-created_at")
        return Response(OrderSerializer(orders, many=True).data)


class AccountOrderDetailView(ClientApiView):
    """GET /api/account/orders/<id>/ — own order detail."""

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        order = get_object_or_404(client.orders.prefetch_related("items__sku"), pk=pk)
        return Response(OrderSerializer(order).data)


class AccountConversationsView(ClientApiView):
    """GET /api/account/conversations/ — own supportchat threads (ЛК-4)."""

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        convs = (
            _scoped_conversations(client)
            .order_by("-updated_at")
            .only("id", "status", "channel", "updated_at", "created_at")
        )
        return Response(
            [
                {
                    "id": c.pk,
                    "subject": f"Диалог #{c.pk}",
                    "status": c.status,
                    "status_label": c.get_status_display(),
                    "channel": c.channel,
                    "channel_label": c.get_channel_display(),
                    "updated_at": c.updated_at,
                }
                for c in convs
            ]
        )


class AccountCompanyView(ClientApiView):
    """GET /api/account/company/ — реквизиты linked Company (ЛК-5)."""

    def get(self, request: Request) -> Response:
        """Requisites only for a manager-confirmed member.

        The company link comes from a free-text name in a lead, so an
        unconfirmed visitor sees only the name they typed themselves.
        """
        client = _client_for(request)
        company = getattr(client, "company_ref", None)
        if company is None or not company.members.filter(client=client, is_confirmed=True).exists():
            return Response(
                {
                    "name": client.company,
                    "inn": "",
                    "legal_address": "",
                    "members": [],
                    "confirmed": False,
                }
            )
        return Response(
            {
                "name": company.name,
                "inn": company.inn,
                "legal_address": company.legal_address,
                "confirmed": True,
                "members": [
                    {
                        "id": m.pk,
                        "role": m.role,
                        "role_label": m.get_role_display(),
                        "client": m.client_id,
                    }
                    for m in company.members.all()
                ],
            }
        )


class AccountRmaView(ClientApiView):
    """GET/POST /api/account/rma/ — reclamations (ЛК-12)."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_repeat"

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        cases = client.rma_cases.order_by("-created_at")
        return Response(RmaCaseSerializer(cases, many=True).data)

    def post(self, request: Request) -> Response:
        client = _client_for(request)
        serializer = RmaCaseCreateSerializer(
            data=request.data,
            context={"client": client},
        )
        serializer.is_valid(raise_exception=True)
        case = serializer.save(client=client)
        from cabinet.tasks import notify_staff_new_rma

        case_id = case.pk
        transaction.on_commit(lambda: notify_staff_new_rma.delay(case_id))
        return Response(RmaCaseSerializer(case).data, status=status.HTTP_201_CREATED)


class AccountRmaPhotoView(ClientApiView):
    """GET /api/account/rma/<id>/photo/ — owner-only defect photo download."""

    def get(self, request: Request, pk: int) -> FileResponse:
        client = _client_for(request)
        case = get_object_or_404(client.rma_cases, pk=pk)
        if not case.photo:
            raise Http404
        return FileResponse(
            case.photo.open("rb"),
            as_attachment=True,
            filename=(case.photo.name or "photo").rsplit("/", 1)[-1],
        )
