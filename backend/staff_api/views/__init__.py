"""Staff mobile API views."""

from __future__ import annotations

import logging
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.admin_otp import AdminOtpDeliveryError, AdminOtpVerifyError
from crm.models import Activity, Client
from crm.services import (
    create_outbound_email,
    scope_clients_for_manager,
)
from leads.models import Lead
from leads.services import (
    apply_lead_manager_on_save,
    count_new_leads,
    scope_leads_for_manager,
    take_lead_in_work,
)
from staff_api.authentication import IsStaffManager, StaffTokenAuthentication
from staff_api.models import StaffAuthToken, StaffDevice
from staff_api.otp import (
    resend_staff_otp,
    staff_api_enabled,
    start_staff_otp,
    verify_staff_otp,
)
from staff_api.serializers import (
    ActivityCreateSerializer,
    DeviceSerializer,
    EmailCreateSerializer,
    LeadStatusSerializer,
    MessageCreateSerializer,
    OtpResendSerializer,
    OtpStartSerializer,
    OtpVerifySerializer,
    serialize_client,
    serialize_conversation,
    serialize_lead,
    serialize_message,
    serialize_user,
)
from supportchat.models import Conversation, ConversationStatus
from supportchat.services import (
    SupportChatError,
    add_staff_reply,
    count_staff_unread,
    delete_unlinked_conversation,
)

logger = logging.getLogger(__name__)


def _feature_disabled() -> Response:
    return Response({"detail": "Staff API выключен."}, status=status.HTTP_404_NOT_FOUND)


def _require_enabled() -> Response | None:
    if not staff_api_enabled():
        return _feature_disabled()
    return None


class StaffPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class StaffAuthMixin:
    authentication_classes = [StaffTokenAuthentication]
    permission_classes = [IsStaffManager]


class OtpStartView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "staff_otp"

    def post(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = OtpStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = start_staff_otp(request._request, ser.validated_data["login"])
        except AdminOtpDeliveryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, **payload})


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "staff_otp"

    def post(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = OtpVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = verify_staff_otp(
                ser.validated_data["challenge_id"],
                ser.validated_data["code"],
            )
        except AdminOtpVerifyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        token = StaffAuthToken.objects.create(user=user)
        return Response({"token": token.key, "user": serialize_user(user)})


class OtpResendView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "staff_otp"

    def post(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = OtpResendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            resend_staff_otp(request._request, ser.validated_data["challenge_id"])
        except AdminOtpDeliveryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True})


class LogoutView(StaffAuthMixin, APIView):
    def post(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        token = getattr(request, "auth", None)
        if isinstance(token, StaffAuthToken):
            token.delete()
        return Response({"ok": True})


class MeView(StaffAuthMixin, APIView):
    def get(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        return Response(serialize_user(request.user))


class BadgesView(StaffAuthMixin, APIView):
    def get(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        return Response(
            {
                "leads_new": count_new_leads(user=request.user),
                "support_unread": count_staff_unread(),
            },
        )


class LeadListView(StaffAuthMixin, APIView):
    def get(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = scope_leads_for_manager(Lead.objects.all(), request.user).order_by("-created_at")
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        paginator = StaffPagination()
        page = paginator.paginate_queryset(qs, request)
        data = [serialize_lead(lead) for lead in page]
        return paginator.get_paginated_response(data)


class LeadDetailView(StaffAuthMixin, APIView):
    def get(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = scope_leads_for_manager(Lead.objects.all(), request.user)
        lead = get_object_or_404(qs, pk=pk)
        from leads.services import mark_lead_seen

        mark_lead_seen(lead.pk)
        lead.refresh_from_db()
        return Response(serialize_lead(lead, detail=True))


class LeadTakeView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = scope_leads_for_manager(Lead.objects.all(), request.user)
        lead = get_object_or_404(qs, pk=pk)
        lead, taken = take_lead_in_work(lead, request.user)
        if not taken:
            return Response(
                {"detail": "Заявку уже взял другой менеджер."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_lead(lead, detail=True))


class LeadStatusView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = LeadStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        qs = scope_leads_for_manager(Lead.objects.all(), request.user)
        lead = get_object_or_404(qs, pk=pk)
        lead.status = ser.validated_data["status"]
        apply_lead_manager_on_save(lead, actor=request.user)
        lead.save()
        return Response(serialize_lead(lead, detail=True))


class ClientListView(StaffAuthMixin, APIView):
    def get(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = scope_clients_for_manager(Client.objects.all(), request.user).order_by("-id")
        q = (request.query_params.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(email__icontains=q) | Q(name__icontains=q) | Q(company__icontains=q),
            )
        paginator = StaffPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response([serialize_client(c) for c in page])


class ClientDetailView(StaffAuthMixin, APIView):
    def get(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = scope_clients_for_manager(Client.objects.all(), request.user)
        client = get_object_or_404(qs, pk=pk)
        return Response(serialize_client(client, detail=True))


class ClientActivityCreateView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = ActivityCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        qs = scope_clients_for_manager(Client.objects.all(), request.user)
        client = get_object_or_404(qs, pk=pk)
        act = Activity.objects.create(
            client=client,
            activity_type=ser.validated_data["activity_type"],
            subject=ser.validated_data.get("subject") or "",
            body=ser.validated_data.get("body") or "",
            author=request.user,
        )
        return Response(
            {
                "id": act.pk,
                "activity_type": act.activity_type,
                "subject": act.subject,
                "body": act.body,
            },
            status=status.HTTP_201_CREATED,
        )


class ClientEmailCreateView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = EmailCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        qs = scope_clients_for_manager(Client.objects.all(), request.user)
        client = get_object_or_404(qs, pk=pk)
        to_email = (ser.validated_data.get("to_email") or "").strip() or None
        msg = create_outbound_email(
            client=client,
            subject=ser.validated_data["subject"],
            body=ser.validated_data["body"],
            to_email=to_email,
            author=request.user,
            send_now=bool(ser.validated_data.get("send_now", True)),
        )
        return Response(
            {"id": msg.pk, "status": msg.status, "subject": msg.subject},
            status=status.HTTP_201_CREATED,
        )


class ConversationListView(StaffAuthMixin, APIView):
    def get(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        qs = (
            Conversation.objects.select_related("client", "lead", "assignee").all().order_by("-last_message_at", "-id")
        )
        st = (request.query_params.get("status") or "").strip()
        if st:
            qs = qs.filter(status=st)
        paginator = StaffPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            [serialize_conversation(c) for c in page],
        )


class ConversationDetailView(StaffAuthMixin, APIView):
    def get(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = get_object_or_404(
            Conversation.objects.select_related("client", "lead", "assignee"),
            pk=pk,
        )
        return Response(serialize_conversation(conv))

    def delete(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = get_object_or_404(Conversation, pk=pk)
        try:
            delete_unlinked_conversation(conv)
        except SupportChatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationMessagesView(StaffAuthMixin, APIView):
    def get(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = get_object_or_404(Conversation, pk=pk)
        qs = conv.messages.order_by("created_at", "id")
        after = request.query_params.get("after")
        if after and str(after).isdigit():
            qs = qs.filter(id__gt=int(after))
        data = [serialize_message(m) for m in qs[:200]]
        resp = Response(data)
        resp["Cache-Control"] = "no-store"
        return resp

    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = MessageCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv = get_object_or_404(Conversation, pk=pk)
        try:
            msg = add_staff_reply(conv, ser.validated_data["body"], author=request.user)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from supportchat.tasks import deliver_outbound_message

        deliver_outbound_message.delay(msg.pk)
        return Response(serialize_message(msg), status=status.HTTP_201_CREATED)


def _conversation_for_staff(*, pk: int) -> Conversation:
    """Load conversation with party FKs for ``serialize_conversation``."""
    return get_object_or_404(
        Conversation.objects.select_related("client", "lead", "assignee"),
        pk=pk,
    )


class ConversationAssignView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = _conversation_for_staff(pk=pk)
        conv.assignee = request.user
        conv.status = ConversationStatus.OPEN
        conv.save(update_fields=["assignee", "status", "updated_at"])
        return Response(serialize_conversation(conv))


class ConversationCloseView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = _conversation_for_staff(pk=pk)
        conv.status = ConversationStatus.CLOSED
        conv.save(update_fields=["status", "updated_at"])
        return Response(serialize_conversation(conv))


class ConversationReadView(StaffAuthMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        conv = _conversation_for_staff(pk=pk)
        conv.staff_unread_count = 0
        conv.save(update_fields=["staff_unread_count", "updated_at"])
        return Response(serialize_conversation(conv))


class DeviceRegisterView(StaffAuthMixin, APIView):
    def post(self, request: Request) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        ser = DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token = ser.validated_data["fcm_token"].strip()
        platform = ser.validated_data["platform"]
        device, _created = StaffDevice.objects.update_or_create(
            fcm_token=token,
            defaults={"user": request.user, "platform": platform},
        )
        return Response(
            {"id": device.pk, "platform": device.platform},
            status=status.HTTP_201_CREATED,
        )


class DeviceDeleteView(StaffAuthMixin, APIView):
    def delete(self, request: Request, pk: int) -> Response:
        blocked = _require_enabled()
        if blocked:
            return blocked
        device = get_object_or_404(StaffDevice, pk=pk, user=request.user)
        device.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
