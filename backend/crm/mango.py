"""Mango VPBX commands API client (исходящие вызовы, записи).

Commands endpoint: ``https://app.mango-office.ru/vpbx/commands/<cmd>``
form-POST ``vpbx_api_key``, ``json``, ``sign`` — та же схема подписи,
что у входящих webhook'ов (``crm.telephony.mango_sign``).

Доступно только когда настроены ``MANGO_VPBX_API_KEY``/``MANGO_VPBX_API_SALT``.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
import uuid
from typing import Any

from django.conf import settings

from crm.telephony import mango_sign

logger = logging.getLogger("hoocon.crm")

_COMMANDS_BASE = "https://app.mango-office.ru/vpbx/commands"
_TIMEOUT_SEC = 15


def mango_configured() -> bool:
    """True когда заданы ключ и соль — без них любые команды бессмысленны."""
    key = (getattr(settings, "MANGO_VPBX_API_KEY", "") or "").strip()
    salt = (getattr(settings, "MANGO_VPBX_API_SALT", "") or "").strip()
    return bool(key and salt)


def mango_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Signed POST to ``commands/<command>``; returns decoded JSON body.

    Raises RuntimeError on transport/HTTP errors — caller maps to a user
    message or a Celery retry.
    """
    key = (getattr(settings, "MANGO_VPBX_API_KEY", "") or "").strip()
    salt = (getattr(settings, "MANGO_VPBX_API_SALT", "") or "").strip()
    if not key or not salt:
        raise RuntimeError("Mango VPBX не настроен (MANGO_VPBX_API_KEY/SALT)")

    json_payload = json.dumps(payload, ensure_ascii=False)
    form = urllib.parse.urlencode(
        {
            "vpbx_api_key": key,
            "sign": mango_sign(key, json_payload, salt),
            "json": json_payload,
        }
    ).encode("utf-8")

    url = f"{_COMMANDS_BASE}/{command}"
    req = urllib.request.Request(url, data=form, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            body = resp.read()
    except OSError as exc:
        raise RuntimeError(f"Mango API недоступен: {exc}") from exc

    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        # recording/post при action=download отдаёт бинарное тело, не JSON
        return {"result": 0, "raw": body}


def initiate_callback(extension: str, to_number: str) -> dict[str, Any]:
    """Click-to-call: Mango звонит на добавочный, затем на номер клиента."""
    payload = {
        "command_id": uuid.uuid4().hex,
        "from": {"extension": extension},
        "to_number": to_number,
        "line_number": "",
    }
    return mango_command("callback", payload)


def webhook_callback_configured() -> bool:
    """True когда задан URL «исходящего звонка через вебхук» из ЛК Mango."""
    return bool(getattr(settings, "MANGO_CALLBACK_WEBHOOK_URL", "").strip())


def initiate_callback_webhook(extension: str, to_number: str) -> None:
    """Click-to-call через интеграцию «Вебхуки» (ЛК → Интеграции → Вебхуки).

    Альтернатива Commands API для тарифов без полного API: GET на URL
    вида ``webhookapp/common?code=…&Action=Callback&EmployeeNUM=…&TelNumbr=…``.
    В URL-шаблоне ``{ext}`` — добавочный менеджера, ``{num}`` — номер клиента.
    Оба значения — только цифры (требование Mango).
    """
    from crm.telephony import normalize_phone_digits

    template = getattr(settings, "MANGO_CALLBACK_WEBHOOK_URL", "").strip()
    if not template:
        raise RuntimeError("Не задан MANGO_CALLBACK_WEBHOOK_URL")
    ext = "".join(ch for ch in extension if ch.isdigit())
    num = normalize_phone_digits(to_number)
    if not ext or not num:
        raise RuntimeError("Пустой добавочный или номер клиента")
    url = template.replace("{ext}", ext).replace("{num}", num)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:
            resp.read()
    except OSError as exc:
        raise RuntimeError(f"Mango webhook недоступен: {exc}") from exc
    logger.info("mango_callback_webhook_sent ext=%s", ext)


def download_recording(recording_id: str) -> bytes | None:
    """Fetch recording file bytes (``recording/post`` action=download)."""
    payload = {
        "command_id": uuid.uuid4().hex,
        "recording_id": recording_id,
        "action": "download",
    }
    result = mango_command("recording/post", payload)
    raw = result.get("raw")
    if isinstance(raw, (bytes, bytearray)) and raw:
        return bytes(raw)
    logger.warning("mango_recording_no_bytes id=%s result=%s", recording_id, result.get("result"))
    return None
