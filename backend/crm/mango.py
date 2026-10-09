"""Mango VPBX API client (исходящие вызовы, записи).

Base ``https://app.mango-office.ru/vpbx/``: ``commands/callback`` для
click-to-call, ``queries/recording/post`` для скачивания записи (302 на
временный файл). Form-POST ``vpbx_api_key``, ``json``, ``sign`` — та же
схема подписи, что у входящих webhook'ов (``crm.telephony.mango_sign``).

Доступно только когда настроены ``MANGO_VPBX_API_KEY``/``MANGO_VPBX_API_SALT``.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
import uuid
from typing import Any

from crm.telephony import mango_sign
from sitesettings.telephony import mango_settings

logger = logging.getLogger("hoocon.crm")

_API_BASE = "https://app.mango-office.ru/vpbx"
_TIMEOUT_SEC = 15
MANGO_RESULT_OK = 1000


def mango_configured() -> bool:
    """True когда виджет включён и заданы ключ и соль."""
    enabled, key, salt, _callback = mango_settings()
    return bool(enabled and key and salt)


def mango_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Signed POST to ``commands/<command>``; returns decoded JSON body."""
    return _mango_post(f"commands/{command}", payload)


def _mango_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Signed POST to ``/vpbx/<path>``; JSON body or ``{"raw": bytes}``.

    Raises RuntimeError on transport/HTTP errors — caller maps to a user
    message or a Celery retry.
    """
    enabled, key, salt, _callback = mango_settings()
    if not enabled:
        raise RuntimeError("Виджет Mango выключен")
    if not key or not salt:
        raise RuntimeError("Mango VPBX не настроен: укажите ключ и соль в виджете")

    json_payload = json.dumps(payload, ensure_ascii=False)
    form = urllib.parse.urlencode(
        {
            "vpbx_api_key": key,
            "sign": mango_sign(key, json_payload, salt),
            "json": json_payload,
        }
    ).encode("utf-8")

    url = f"{_API_BASE}/{path}"
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
    result = mango_command("callback", payload)
    code = result.get("result")
    if code != MANGO_RESULT_OK:
        raise RuntimeError(f"Mango отклонил звонок: код {code}")
    return result


def webhook_callback_configured() -> bool:
    """True когда виджет включён и задан URL исходящего звонка из ЛК Mango."""
    enabled, _key, _salt, callback = mango_settings()
    return bool(enabled and callback)


def callback_template_error(template: str) -> str:
    """Why a callback URL template is unsafe, or ``""`` when it is fine.

    ``urlopen`` also opens ``file://`` / ``ftp://`` and plain-http internal
    hosts, so only an absolute ``https://`` URL is accepted.
    """
    parsed = urllib.parse.urlsplit((template or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return "URL вебхука Mango должен начинаться с https:// и содержать адрес сервера."
    return ""


def initiate_callback_webhook(extension: str, to_number: str) -> None:
    """Click-to-call через интеграцию «Вебхуки» (ЛК → Интеграции → Вебхуки).

    Альтернатива Commands API для тарифов без полного API: GET на URL
    вида ``webhookapp/common?code=…&Action=Callback&EmployeeNUM=…&TelNumbr=…``.
    В URL-шаблоне ``{ext}`` — добавочный менеджера, ``{num}`` — номер клиента.
    Оба значения — только цифры (требование Mango).
    """
    from crm.telephony import normalize_phone_digits

    enabled, _key, _salt, template = mango_settings()
    if not enabled:
        raise RuntimeError("Виджет Mango выключен")
    if not template:
        raise RuntimeError("Не задан URL вебхука исходящего звонка Mango")
    ext = "".join(ch for ch in extension if ch.isdigit())
    num = normalize_phone_digits(to_number)
    if not ext or not num:
        raise RuntimeError("Пустой добавочный или номер клиента")
    problem = callback_template_error(template)
    if problem:
        raise RuntimeError(problem)
    url = template.replace("{ext}", ext).replace("{num}", num)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:
            resp.read()
    except OSError as exc:
        raise RuntimeError(f"Mango webhook недоступен: {exc}") from exc
    logger.info("mango_callback_webhook_sent ext=%s", ext)


def download_recording(recording_id: str) -> bytes | None:
    """Fetch recording bytes (``queries/recording/post``; urllib follows the 302)."""
    payload = {
        "command_id": uuid.uuid4().hex,
        "recording_id": recording_id,
        "action": "download",
    }
    result = _mango_post("queries/recording/post", payload)
    raw = result.get("raw")
    if isinstance(raw, (bytes, bytearray)) and raw:
        return bytes(raw)
    logger.warning("mango_recording_no_bytes id=%s result=%s", recording_id, result.get("result"))
    return None
