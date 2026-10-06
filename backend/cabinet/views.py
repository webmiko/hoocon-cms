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
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import ClientAccount
from cabinet.auth import IsClientAccount, load_client_account, login_client, logout_client
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
    authenticate_password,
    check_honeypot,
    register_client,
    resend_client_otp,
    start_client_otp,
    verify_client_otp,
)
from crm.models import Client, QuoteStatus
from leads.models import Lead

logger = logging.getLogger(__name__)

_REPEAT_WINDOW_SECONDS = 300


def _client_for(request: Request) -> Client:
    """Resolve the CRM card of the session account (404-safe)."""
    account = load_client_account(request)
    if account is None:
        raise Http404
    client, _ = Client.objects.get_or_create(
        email=account.email,
        defaults={"name": account.name or account.email, "phone": account.phone},
    )
    if client.account_id is None:
        client.account = account
        client.save(update_fields=["account", "updated_at"])
    return client


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


class RegisterView(APIView):
    """POST /api/auth/register/ — mode A (email + password), honeypot-gated."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_auth"

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            check_honeypot(request, data.get("form_start_ts"), data.get("website", ""))
            account = register_client(
                email=data["email"],
                password=data["password"],
                name=data.get("name", ""),
                phone=data.get("phone", ""),
            )
        except ClientAuthError as exc:
            # Honeypot/validation errors share one shape — no detail leaks.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        login_client(request._request, account)  # noqa: SLF001 — DRF wraps HttpRequest
        return Response(_account_payload(account), status=status.HTTP_201_CREATED)


class LoginView(APIView):
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
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        login_client(request._request, account)  # noqa: SLF001
        return Response(_account_payload(account))


class OtpStartView(APIView):
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
            result = start_client_otp(request._request, data["email"])  # noqa: SLF001
        except ClientAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class OtpVerifyView(APIView):
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
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        login_client(request._request, account)  # noqa: SLF001
        return Response(_account_payload(account))


class OtpResendView(APIView):
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
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class LogoutView(APIView):
    """POST /api/auth/logout/ — drop the client session."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        logout_client(request._request)  # noqa: SLF001
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthMeView(APIView):
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


class AccountMeView(APIView):
    """GET/PATCH /api/account/me/ — cabinet profile."""

    permission_classes = (IsClientAccount,)
    authentication_classes = ()  # session already resolved via load_client_account

    def get(self, request: Request) -> Response:
        account = load_client_account(request)
        return Response(_account_payload(account))  # type: ignore[arg-type]

    def patch(self, request: Request) -> Response:
        account = load_client_account(request)
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


class AccountSummaryView(APIView):
    """GET /api/account/summary/ — dashboard counters."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        from supportchat.models import Conversation, ConversationStatus

        return Response(
            {
                "active_leads": client.leads.exclude(status=Lead.LeadStatus.DONE).count(),
                "quotes_pending": client.quotes.filter(status=QuoteStatus.SENT).count(),
                "orders_in_work": client.orders.exclude(status__in=("done", "cancelled")).count(),
                "unread_conversations": Conversation.objects.filter(
                    client=client,
                    status=ConversationStatus.OPEN,
                ).count(),
            }
        )


def _scoped_leads(client: Client) -> QuerySet[Lead]:
    return client.leads.prefetch_related("items__sku").order_by("-created_at")


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


class AccountLeadsView(APIView):
    """GET /api/account/leads/ — own leads only."""

    permission_classes = (IsClientAccount,)
    pagination_class = PageNumberPagination

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        leads = _scoped_leads(client)
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            leads = leads.filter(status=status_filter)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(leads, request)
        return paginator.get_paginated_response([_lead_payload(lead) for lead in page] if page else [])


class AccountLeadDetailView(APIView):
    """GET /api/account/leads/<id>/ — own lead detail (404 on foreign)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        lead = get_object_or_404(_scoped_leads(client), pk=pk)
        payload = _lead_payload(lead)
        payload["quotes"] = QuoteSerializer(lead.quotes.all(), many=True).data
        return Response(payload)


class AccountLeadRepeatView(APIView):
    """POST /api/account/leads/<id>/repeat/ — clone positions into a new RFQ.

    Idempotent within a 5-minute window (§9): a repeat of the same source
    lead returns the already-created copy instead of spawning duplicates.
    """

    permission_classes = (IsClientAccount,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_repeat"

    def post(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        source = get_object_or_404(_scoped_leads(client), pk=pk)
        recent = (
            Lead.objects.filter(
                client=client,
                created_at__gte=timezone.now() - timedelta(seconds=_REPEAT_WINDOW_SECONDS),
                message__contains=f"#{source.pk}",
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
                message=f"Повтор заявки #{source.pk}",
            )
            for item in source.items.all():
                lead.items.create(
                    sku=item.sku,
                    sku_code=item.sku_code,
                    quantity=item.quantity,
                    sort_order=item.sort_order,
                )
        return Response(_lead_payload(lead), status=status.HTTP_201_CREATED)


class AccountSpecsView(APIView):
    """GET/POST /api/account/specs/ — spec templates CRUD (owner scope)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        account = load_client_account(request)
        specs = SpecList.objects.filter(account=account).prefetch_related("items__sku").order_by("-updated_at")
        return Response(SpecListSerializer(specs, many=True).data)

    def post(self, request: Request) -> Response:
        account = load_client_account(request)
        serializer = SpecListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spec = _save_spec(account, serializer.validated_data)  # type: ignore[arg-type]
        return Response(SpecListSerializer(spec).data, status=status.HTTP_201_CREATED)


class AccountSpecDetailView(APIView):
    """GET/PATCH/DELETE /api/account/specs/<id>/ — owner scope."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> Response:
        account = load_client_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account).prefetch_related("items__sku"), pk=pk)
        return Response(SpecListSerializer(spec).data)

    def patch(self, request: Request, pk: int) -> Response:
        account = load_client_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account), pk=pk)
        serializer = SpecListWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        spec = _save_spec(account, serializer.validated_data, spec=spec)  # type: ignore[arg-type]
        return Response(SpecListSerializer(spec).data)

    def delete(self, request: Request, pk: int) -> Response:
        account = load_client_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account), pk=pk)
        spec.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountSpecToLeadView(APIView):
    """POST /api/account/specs/<id>/to_lead/ — draft an RFQ from a spec."""

    permission_classes = (IsClientAccount,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "client_repeat"

    def post(self, request: Request, pk: int) -> Response:
        account = load_client_account(request)
        spec = get_object_or_404(SpecList.objects.filter(account=account).prefetch_related("items"), pk=pk)
        client = _client_for(request)
        with transaction.atomic():
            lead = Lead.objects.create(
                lead_type=Lead.LeadType.RFQ,
                name=client.name or client.email,
                email=client.email,
                phone=client.phone,
                company=client.company,
                message=f"Заявка из спецификации «{spec.name}»",
            )
            for item in spec.items.all():
                lead.items.create(
                    sku=item.sku,
                    sku_code=item.sku_code,
                    quantity=item.quantity,
                    sort_order=item.position,
                )
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
                sku = None
                sku_id = raw.get("sku")
                if sku_id:
                    sku = SKU.objects.filter(pk=sku_id).first()
                elif code:
                    sku = SKU.objects.filter(sku_code__iexact=code).first()
                spec.items.create(
                    sku=sku,
                    sku_code=code or (sku.sku_code if sku else ""),
                    quantity=max(int(raw.get("quantity") or 1), 1),
                    position=int(raw.get("position") or idx),
                )
    return spec


class AccountQuotesView(APIView):
    """GET /api/account/quotes/ — issued quotes (drafts hidden)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        quotes = client.quotes.exclude(status=QuoteStatus.DRAFT).prefetch_related("items").order_by("-created_at")
        return Response(QuoteSerializer(quotes, many=True).data)


class AccountQuoteDetailView(APIView):
    """GET /api/account/quotes/<id>/ — own quote detail."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        quote = get_object_or_404(
            client.quotes.exclude(status=QuoteStatus.DRAFT).prefetch_related("items__sku"),
            pk=pk,
        )
        return Response(QuoteSerializer(quote).data)


class AccountQuotePdfView(APIView):
    """GET /api/account/quotes/<id>/pdf/ — generated PDF (ЛК-3)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> FileResponse:
        client = _client_for(request)
        quote = get_object_or_404(client.quotes.exclude(status=QuoteStatus.DRAFT), pk=pk)
        from crm.quote_pdf import render_quote_pdf

        pdf = render_quote_pdf(quote)
        return FileResponse(pdf, content_type="application/pdf", filename=f"{quote.number}.pdf")


class AccountDocumentsView(APIView):
    """GET /api/account/documents/ — all files of the client card."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        docs = client.documents.order_by("-created_at")
        return Response(DocumentSerializer(docs, many=True).data)


class AccountDocumentDownloadView(APIView):
    """GET /api/account/documents/<id>/download/ — owner-only private file."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> FileResponse:
        client = _client_for(request)
        doc = get_object_or_404(client.documents, pk=pk)
        return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.title)


class AccountDocumentsZipView(APIView):
    """GET /api/account/documents/zip/ — все документы клиента одним ZIP (ЛК-8).

    Files come from private media only; names are sanitized against
    path traversal and de-duplicated inside the archive.
    """

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> FileResponse:
        import io
        import zipfile

        from catalog.validators import sanitize_upload_filename

        client = _client_for(request)
        docs = client.documents.order_by("kind", "created_at")
        buf = io.BytesIO()
        used_names: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in docs:
                if not doc.file:
                    continue
                base = sanitize_upload_filename(doc.title or f"document-{doc.pk}")
                name = base
                n = 2
                while name in used_names:
                    stem, dot, ext = base.rpartition(".")
                    name = f"{stem}-{n}.{ext}" if dot else f"{base}-{n}"
                    n += 1
                used_names.add(name)
                with doc.file.open("rb") as fh:
                    zf.writestr(name, fh.read())
        buf.seek(0)
        filename = f"hoocon-docs-{client.pk}.zip"
        return FileResponse(buf, as_attachment=True, filename=filename)


class AccountOrdersView(APIView):
    """GET /api/account/orders/ — own orders (ЛК-6)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        orders = client.orders.prefetch_related("items__sku").order_by("-created_at")
        return Response(OrderSerializer(orders, many=True).data)


class AccountOrderDetailView(APIView):
    """GET /api/account/orders/<id>/ — own order detail."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request, pk: int) -> Response:
        client = _client_for(request)
        order = get_object_or_404(client.orders.prefetch_related("items__sku"), pk=pk)
        return Response(OrderSerializer(order).data)


class AccountConversationsView(APIView):
    """GET /api/account/conversations/ — own supportchat threads (ЛК-4)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        from supportchat.models import Conversation

        client = _client_for(request)
        convs = (
            Conversation.objects.filter(client=client)
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


class AccountCompanyView(APIView):
    """GET /api/account/company/ — реквизиты linked Company (ЛК-5)."""

    permission_classes = (IsClientAccount,)

    def get(self, request: Request) -> Response:
        client = _client_for(request)
        company = getattr(client, "company_ref", None)
        if company is None:
            return Response(
                {
                    "name": client.company,
                    "inn": "",
                    "legal_address": "",
                    "members": [],
                }
            )
        return Response(
            {
                "name": company.name,
                "inn": company.inn,
                "legal_address": company.legal_address,
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


class AccountRmaView(APIView):
    """GET/POST /api/account/rma/ — reclamations (ЛК-12)."""

    permission_classes = (IsClientAccount,)
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
        return Response(RmaCaseSerializer(case).data, status=status.HTTP_201_CREATED)


class AccountRmaPhotoView(APIView):
    """GET /api/account/rma/<id>/photo/ — owner-only defect photo download."""

    permission_classes = (IsClientAccount,)

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
