"""Mango VPBX telephony: event signature check, parsing, Call upsert.

Подпись запросов Mango: ``sha256(vpbx_api_key + json + vpbx_api_salt)``
(hex). События приходят form-POST'ом на ``/api/telephony/mango/events/`` —
``vpbx_api_key``, ``sign``, ``json`` (строка). Один URL принимает оба типа
событий: ``call`` (состояние вызова) и ``recording`` (готовность записи).

Резолв: клиент ищется по нормализованным цифрам телефона
(``Client.phone_digits``), менеджер — по добавочному
(``accounts.StaffVpbxProfile.extension``). По завершении разговора
(Disconnected) на карточку клиента пишется Activity «Звонок».
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from crm.models import (
    Activity,
    ActivityType,
    Call,
    CallDirection,
    CallState,
    Client,
)

logger = logging.getLogger("hoocon.crm")

_DIGITS_RE = re.compile(r"\D+")


def normalize_phone_digits(phone: str) -> str:
    """Reduce a phone string to digits in RU E.164-ish form (7…).

    ``+7 (495) 123-45-67`` and ``8 495 1234567`` → ``74951234567``;
    короткие добавочные возвращаем как есть.
    """
    digits = _DIGITS_RE.sub("", phone or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return digits


def mango_sign(api_key: str, json_payload: str, api_salt: str) -> str:
    """Signature scheme shared by events webhooks and commands API."""
    raw = f"{api_key}{json_payload}{api_salt}".encode()
    return hashlib.sha256(raw).hexdigest()


def verify_mango_signature(api_key: str, json_payload: str, sign: str) -> bool:
    """Constant-time signature check; False when the widget is off or keys are empty."""
    from sitesettings.telephony import mango_settings

    enabled, expected_key, salt, _callback = mango_settings()
    api_key = (api_key or "").strip()
    if not enabled or not expected_key or not salt or api_key != expected_key:
        return False
    expected = mango_sign(api_key, json_payload, salt)
    return hmac.compare_digest(expected, (sign or "").strip())


def _epoch(ts: Any) -> Any:
    """Mango timestamps are epoch seconds; tolerate junk."""
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(int(ts), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _endpoint_number(endpoint: Any) -> str:
    """Pick the external phone number out of a Mango from/to object."""
    if not isinstance(endpoint, dict):
        return ""
    return (endpoint.get("number") or endpoint.get("line_number") or "").strip()


def _endpoint_extension(endpoint: Any) -> str:
    if not isinstance(endpoint, dict):
        return ""
    return (endpoint.get("extension") or "").strip()


def _client_and_extension(payload: dict[str, Any]) -> tuple[str, str]:
    """Client-facing number + manager extension from a call event."""
    from_ep = payload.get("from") or {}
    to_ep = payload.get("to") or {}
    ext_from = _endpoint_extension(from_ep)
    ext_to = _endpoint_extension(to_ep)
    if ext_from and not ext_to:
        # Исходящий: менеджер (extension) → клиент (number).
        return _endpoint_number(to_ep), ext_from
    if ext_to and not ext_from:
        # Входящий: клиент (number) → менеджер (extension).
        return _endpoint_number(from_ep), ext_to
    # Внутренний/неоднозначный — берём from как «внешний», extension из to.
    return _endpoint_number(from_ep), ext_to or ext_from


def _resolve_client(client_number: str) -> Client | None:
    """Find the CRM card by normalized phone digits."""
    digits = normalize_phone_digits(client_number)
    if len(digits) < 5:
        return None
    return Client.objects.filter(phone_digits=digits).exclude(phone_digits="").order_by("id").first()


def _resolve_manager(extension: str) -> Any:
    """Staff user bound to this Mango extension (StaffVpbxProfile)."""
    if not extension:
        return None
    from accounts.models import StaffVpbxProfile

    profile = StaffVpbxProfile.objects.filter(extension=extension, is_enabled=True).select_related("user").first()
    return profile.user if profile else None


def _latest_open_lead(client: Client | None) -> Any:
    """Attach the call to the client's newest unfinished lead, if any."""
    if client is None:
        return None
    from leads.models import Lead

    return client.leads.exclude(status=Lead.LeadStatus.DONE).order_by("-created_at").first()


def _fmt_duration(seconds: int) -> str:
    """'1:23' style duration for the activity line."""
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds else "0:00"


def handle_mango_event(payload: dict[str, Any]) -> str:
    """Route one decoded Mango event; return a short verdict for logging.

    ``call`` / ``recording`` — обработано; ``ignored`` — чужой тип или
    бесполезный seq; ``skipped`` — нет entry_id.
    """
    if not isinstance(payload, dict):
        return "skipped"
    if payload.get("recording_id") or payload.get("recording_state"):
        return _handle_recording_event(payload)
    if payload.get("call_state"):
        return _handle_call_event(payload)
    return "ignored"


def _handle_call_event(payload: dict[str, Any]) -> str:
    """Upsert Call by entry_id; Activity once on first Disconnected."""
    entry_id = (payload.get("entry_id") or "").strip()
    if not entry_id:
        return "skipped"

    seq = int(payload.get("seq") or 0)
    state_raw = str(payload.get("call_state") or "").lower()
    state = _map_state(state_raw)
    client_number, extension = _client_and_extension(payload)
    direction = CallDirection.OUTBOUND if _endpoint_extension(payload.get("from")) else CallDirection.INBOUND
    from_number = _endpoint_number(payload.get("from"))
    to_number = _endpoint_number(payload.get("to"))
    ts = _epoch(payload.get("timestamp")) or timezone.now()

    with transaction.atomic():
        call, created = Call.objects.select_for_update().get_or_create(
            entry_id=entry_id,
            defaults={
                "call_id": (payload.get("call_id") or "")[:200],
                "direction": direction,
                "state": state,
                "from_number": from_number[:32],
                "to_number": to_number[:32],
                "extension": extension[:20],
                "started_at": ts,
                "last_seq": seq,
            },
        )
        if not created:
            if seq and seq <= call.last_seq:
                return "ignored"  # устаревшее событие / ретрай
            call.call_id = call.call_id or (payload.get("call_id") or "")[:200]
            call.state = state
            call.from_number = from_number[:32] or call.from_number
            call.to_number = to_number[:32] or call.to_number
            call.extension = extension[:20] or call.extension
            call.last_seq = seq or call.last_seq

        if call.client_id is None:
            call.client = _resolve_client(client_number)  # type: ignore[assignment]
        if call.manager_id is None:
            call.manager = _resolve_manager(extension)  # type: ignore[assignment]
        if call.lead_id is None:
            resolved_client = cast(Client | None, call.client)
            call.lead = _latest_open_lead(resolved_client)

        if state == CallState.CONNECTED and call.connected_at is None:
            call.connected_at = ts
        if state == CallState.DISCONNECTED and call.finished_at is None:
            call.finished_at = ts
            if call.connected_at:
                call.talk_duration = max(0, int((ts - call.connected_at).total_seconds()))
        call.save()
        first_disconnect = state == CallState.DISCONNECTED and call.finished_at == ts

    if first_disconnect:
        _log_call_activity(call)
        logger.info("mango_call_finished entry=%s talk=%ss", entry_id, call.talk_duration)
    return "call"


def _handle_recording_event(payload: dict[str, Any]) -> str:
    """Recording readiness: store recording_id, enqueue download."""
    entry_id = (payload.get("entry_id") or "").strip()
    recording_id = (payload.get("recording_id") or "").strip()
    if not entry_id or not recording_id:
        return "skipped"
    state = str(payload.get("recording_state") or "").lower()
    updated = Call.objects.filter(entry_id=entry_id, recording_id="").update(recording_id=recording_id[:200])
    if state == "completed":
        from crm.tasks import fetch_mango_recording

        try:
            fetch_mango_recording.delay(entry_id)
        except Exception:  # noqa: BLE001 — вебхук не должен падать из-за брокера
            logger.exception("mango_recording_enqueue_failed entry=%s", entry_id)
    logger.info("mango_recording entry=%s state=%s linked=%s", entry_id, state, bool(updated))
    return "recording"


def _map_state(call_state: str) -> str:
    return {
        "appeared": CallState.APPEARED,
        "connected": CallState.CONNECTED,
        "disconnected": CallState.DISCONNECTED,
        "onhold": CallState.ON_HOLD,
        "transferred": CallState.TRANSFERRED,
        "initiated": CallState.INITIATED,
    }.get(call_state, CallState.APPEARED)


def _log_call_activity(call: Call) -> None:
    """Timeline entry on the client card (and latest lead) for the call."""
    if call.client_id is None and call.lead_id is None:
        return
    direction_label = "Исходящий звонок" if call.direction == CallDirection.OUTBOUND else "Входящий звонок"
    parts = [f"{call.from_number or '—'} → {call.to_number or '—'}"]
    if call.talk_duration:
        parts.append(f"разговор {_fmt_duration(call.talk_duration)}")
    if call.extension:
        parts.append(f"доб. {call.extension}")
    client = cast(Client | None, call.client)
    lead = cast(Any, call.lead)
    if client is None and lead is not None:
        client = cast(Client | None, lead.client)
    if client is None:
        return
    Activity.objects.create(
        client=client,
        lead=lead,
        activity_type=ActivityType.CALL,
        subject=direction_label,
        body="; ".join(parts),
    )
