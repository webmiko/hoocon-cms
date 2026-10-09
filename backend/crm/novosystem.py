"""Novosystem (UIS) Call API and inbound webhook.

Call API: JSON-RPC 2.0 ``POST https://callapi.uiscom.ru/v4.0``.
Вебхук — HTTP на наш URL; секрет передаётся параметром ``token``.
Звонки пишутся в тот же журнал ``Call`` с префиксом ``uis:`` у ``entry_id``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any, cast

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from crm.models import Call, CallDirection, CallState, Client
from crm.telephony import (
    _latest_open_lead,
    _log_call_activity,
    _resolve_client,
    _resolve_manager,
    normalize_phone_digits,
)
from sitesettings.telephony import novosystem_settings

logger = logging.getLogger("hoocon.crm")

_CALL_API = "https://callapi.uiscom.ru/v4.0"
_TIMEOUT_SEC = 15


def novosystem_configured() -> bool:
    """True when the widget is on and token plus virtual number are set."""
    enabled, token, phone, _secret = novosystem_settings()
    return bool(enabled and token and phone)


def webhook_token_ok(presented: str) -> bool:
    """True when the widget is on and ``presented`` matches the saved secret."""
    from config.secret_compare import secrets_equal

    enabled, _token, _phone, secret = novosystem_settings()
    presented = (presented or "").strip()
    if not enabled or not secret or not presented:
        return False
    return secrets_equal(secret, presented)


def initiate_employee_call(*, employee_id: str, employee_phone: str, contact: str) -> int:
    """Click-to-call: UIS rings the employee, then the client.

    Args:
        employee_id: Numeric UIS employee id.
        employee_phone: Active phone or extension of that employee.
        contact: Client number, digits only.

    Returns:
        ``call_session_id`` from UIS.

    Raises:
        RuntimeError: Widget off, incomplete settings, or API error.
    """
    enabled, token, virtual, _secret = novosystem_settings()
    if not enabled:
        raise RuntimeError("Виджет Новосистем выключен")
    if not token or not virtual:
        raise RuntimeError("Новосистем не настроен: укажите ключ и виртуальный номер в виджете")
    employee = "".join(ch for ch in employee_id if ch.isdigit())
    contact_digits = normalize_phone_digits(contact)
    if not employee or not contact_digits:
        raise RuntimeError("Нужны ID сотрудника UIS и телефон клиента")
    params: dict[str, Any] = {
        "access_token": token,
        "first_call": "employee",
        "direction": "out",
        "virtual_phone_number": virtual,
        "contact": contact_digits,
        "employee": {"id": int(employee)},
    }
    phone = normalize_phone_digits(employee_phone)
    # Короткий добавочный Mango — не телефон UIS. Иначе Call API звонит на «101».
    if len(phone) >= 10:
        params["employee"]["phone_number"] = phone
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "start.employee_call",
            "id": "hoocon-click",
            "params": params,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        _CALL_API,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Новосистем отклонил вызов: {_uis_error_message(exc)}") from exc
    except OSError as exc:
        raise RuntimeError(f"Новосистем API недоступен: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("Новосистем вернул не JSON") from exc
    if payload.get("error"):
        message = payload["error"].get("message") if isinstance(payload["error"], dict) else payload["error"]
        raise RuntimeError(f"Новосистем отклонил вызов: {message}")
    data = (payload.get("result") or {}).get("data") or {}
    session_id = data.get("call_session_id")
    if isinstance(session_id, bool) or not isinstance(session_id, int | str):
        raise RuntimeError("Новосистем не вернул идентификатор звонка")
    try:
        return int(session_id)
    except ValueError as exc:
        raise RuntimeError("Новосистем не вернул идентификатор звонка") from exc


def _uis_error_message(exc: urllib.error.HTTPError) -> str:
    """Text from a UIS HTTP error body, or the status code."""
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return f"HTTP {exc.code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:300]
    return f"HTTP {exc.code}"


def _parse_uis_time(value: Any) -> datetime | None:
    """UIS ``start_time`` / ``finish_time``: unix seconds, ISO, or ``YYYY-MM-DD HH:MM:SS``."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_unix(float(value))
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _from_unix(float(text))
    parsed = parse_datetime(text)
    if parsed is None and " " in text:
        parsed = parse_datetime(text.replace(" ", "T", 1))
    if parsed is None:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _from_unix(seconds: float) -> datetime | None:
    """Unix seconds, or milliseconds when the value is too large for seconds."""
    if seconds > 10_000_000_000:
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _talk_seconds(value: Any) -> int:
    """Duration from UIS; floats and numeric strings become whole seconds."""
    if value in (None, ""):
        return 0
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _resolve_uis_manager(employee_id: Any, extension: str) -> Any:
    """Staff user by UIS employee id, then by the Mango/UIS extension."""
    from django.db.models import Q

    from accounts.models import StaffVpbxProfile

    raw = str(employee_id or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        profile = (
            StaffVpbxProfile.objects.filter(is_enabled=True)
            .filter(Q(uis_employee_id=digits) | Q(uis_employee_id=raw))
            .select_related("user")
            .first()
        )
        if profile is not None:
            return profile.user
    return _resolve_manager(extension) if extension else None


@transaction.atomic
def handle_novosystem_event(payload: dict[str, Any]) -> str:
    """Upsert a Call row from a UIS webhook body.

    Args:
        payload: JSON or form fields of one notification.

    Returns:
        ``created``, ``updated``, or ``ignored``.
    """
    session = str(payload.get("call_session_id") or payload.get("id") or "").strip()
    if not session:
        return "ignored"
    entry_id = f"uis:{session}"[:128]
    direction_raw = str(payload.get("direction") or "in").lower()
    direction = CallDirection.OUTBOUND if direction_raw in {"out", "outbound"} else CallDirection.INBOUND
    raw_contact = payload.get("contact_phone_number") or payload.get("calling_phone_number") or ""
    contact = normalize_phone_digits(str(raw_contact))
    virtual = normalize_phone_digits(str(payload.get("virtual_phone_number") or ""))
    extension = str(payload.get("extension") or "").strip()[:20]
    if direction == CallDirection.INBOUND:
        from_number, to_number = contact, virtual
    else:
        from_number, to_number = virtual, contact
    is_lost = str(payload.get("is_lost") or "").lower() in {"1", "true", "yes"}
    talk_duration = _talk_seconds(payload.get("talk_duration") or payload.get("talk_time_duration"))
    started = _parse_uis_time(payload.get("start_time"))
    raw_finish = payload.get("finish_time")
    finished = _parse_uis_time(raw_finish)
    has_finish = raw_finish not in (None, "", 0, "0", False)
    state = CallState.DISCONNECTED if has_finish or is_lost else CallState.APPEARED
    recording_id = str(payload.get("recording_id") or "")
    records = payload.get("call_records")
    if not recording_id and isinstance(records, list) and records:
        recording_id = str(records[0])
    recording_id = recording_id[:200]
    now = timezone.now()
    client = _resolve_client(contact)
    manager = _resolve_uis_manager(payload.get("employee_id"), extension)
    call, created = Call.objects.select_for_update().get_or_create(
        entry_id=entry_id,
        defaults={
            "call_id": session[:200],
            "direction": direction,
            "state": state,
            "from_number": from_number[:32],
            "to_number": to_number[:32],
            "extension": extension,
            "client": client,
            "lead": _latest_open_lead(client) if client else None,
            "manager": manager,
            "started_at": started or now,
            "talk_duration": talk_duration,
            "recording_id": recording_id,
            "finished_at": (finished or now) if state == CallState.DISCONNECTED else None,
        },
    )
    previously_finished = not created and call.state == CallState.DISCONNECTED
    if not created:
        if not previously_finished:
            call.direction = direction
            call.state = state
            call.from_number = from_number[:32] or call.from_number
            call.to_number = to_number[:32] or call.to_number
        call.extension = extension or call.extension
        call.talk_duration = talk_duration or call.talk_duration
        call.recording_id = recording_id or call.recording_id
        if client and call.client_id is None:
            call.client = client
        if manager and call.manager_id is None:
            call.manager = manager
        if started is not None and (call.started_at is None or started < call.started_at):
            call.started_at = started
        if state == CallState.DISCONNECTED and call.finished_at is None:
            call.finished_at = finished or now
            call.state = CallState.DISCONNECTED
        if call.client_id and call.lead_id is None:
            call.lead = _latest_open_lead(cast(Client | None, call.client))
        call.save()
    if state == CallState.DISCONNECTED and not previously_finished:
        _log_call_activity(call)
    return "created" if created else "updated"
