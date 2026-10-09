"""Public Lead API: POST /api/leads/ (honeypot + throttle + Celery email).

Spec: ПЛАН §6 Iter 3 — Lead API + Celery email + honeypot + throttle;
docs/security-baseline.md §3 (PII не в логах; honeypot silent drop; 429 на throttle).

Контракт:
- POST /api/leads/ — публичный (AllowAny); throttle scope `lead_create` (10/hour).
- Honeypot: поле `website` заполнено → 201 silent drop (заявка не создаётся,
  email не отправляется). Боты думают, что форма отправлена.
- После успешного создания — Celery-таски send_lead_notification (менеджеру)
  и send_lead_client_confirmation (клиенту) через transaction.on_commit
  (стартуют только после коммита БД).
- PII-safe: email/phone — write-only в сериализаторе (нет в ответе).
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from cabinet.auth import session_owns_email
from config.logging_utils import setup_logger
from leads.lifecycle import on_lead_created
from leads.models import Lead
from leads.serializers import LeadSerializer

logger = setup_logger("hoocon.leads")

# Throttle scope name (matches REST_FRAMEWORK.DEFAULT_THROTTLE_RATES).
_LEAD_THROTTLE_SCOPE = "lead_create"


class LeadViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """POST /api/leads/ — public lead creation with honeypot + throttle.

    GET is not allowed (write-only endpoint). The view enforces:
    - ScopedRateThrottle on `lead_create` (10/hour per IP).
    - Honeypot silent drop: if `website` field is filled, returns 201
      but does NOT create a Lead or send email.
    - Assignee: ООО Атерна → assistant@hoocon.ru; else round-robin when enabled.
    - Celery task `send_lead_notification` fires via transaction.on_commit
      after successful creation.
    """

    serializer_class = LeadSerializer
    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _LEAD_THROTTLE_SCOPE
    http_method_names = ["post", "head", "options"]
    queryset = Lead.objects.none()  # write-only; no list/retrieve

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Handle POST: validate, honeypot check, create, schedule email.

        Args:
            request: DRF request with lead payload.

        Returns:
            201 with serialized lead (PII-safe: no email/phone in response),
            or 201 silent drop if honeypot is filled (no lead created),
            or 400 on validation errors.
        """
        # Honeypot before validation: bots skip required RFQ fields; do not
        # teach them about company/items rules via 400 responses.
        payload = request.data if isinstance(request.data, dict) else {}
        raw_website = payload.get("website") or ""
        if isinstance(raw_website, (list, tuple)):
            raw_website = raw_website[0] if raw_website else ""
        if str(raw_website).strip():
            logger.info("Honeypot hit — silent drop (no lead created)")
            return Response({"id": None, "status": "new"}, status=status.HTTP_201_CREATED)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        if session_owns_email(request, lead.email):
            Lead.objects.filter(pk=lead.pk).update(contact_verified=True)
            lead.contact_verified = True

        on_lead_created(lead)

        return Response(
            LeadSerializer(lead, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )
