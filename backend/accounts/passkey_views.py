"""Admin WebAuthn passkey views (register / login / manage)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from django.contrib import admin, messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.signals import user_login_failed
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from accounts.models import PasskeyCredential
from accounts.passkeys import (
    admin_passkey_enabled,
    begin_authentication,
    begin_registration,
    clear_authentication_challenge,
    clear_registration_challenge,
    complete_authentication,
    complete_registration,
    passkeys_for_user,
)

logger = logging.getLogger(__name__)


def _json_error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _parse_json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Некорректный JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект.")
    return data


def _safe_next_url(raw: str) -> str:
    """Allow only same-site relative admin paths."""
    candidate = (raw or "").strip() or "/admin/"
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return "/admin/"
    if not candidate.startswith("/"):
        return "/admin/"
    return candidate


def _require_enabled() -> HttpResponse | None:
    if not admin_passkey_enabled():
        return HttpResponseNotFound("Passkeys disabled")
    return None


def _require_staff(request: HttpRequest) -> HttpResponse | None:
    user = request.user
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return redirect_to_login(request.get_full_path(), login_url=reverse("admin:login"))
    return None


def _record_login_failure(request: HttpRequest, *, username: str = "passkey") -> None:
    user_login_failed.send(
        sender=__name__,
        credentials={"username": username},
        request=request,
    )


@require_POST
def passkey_register_begin(request: HttpRequest) -> HttpResponse:
    """POST → PublicKeyCredentialCreationOptions for the logged-in staff user."""
    blocked = _require_enabled() or _require_staff(request)
    if blocked is not None:
        return blocked
    try:
        options = begin_registration(request, request.user)
    except Exception:  # noqa: BLE001
        logger.exception("passkey register begin failed")
        return _json_error("Не удалось начать регистрацию ключа.", status=500)
    return JsonResponse({"ok": True, "publicKey": options})


@require_POST
def passkey_register_complete(request: HttpRequest) -> HttpResponse:
    """POST JSON credential → save PasskeyCredential."""
    blocked = _require_enabled() or _require_staff(request)
    if blocked is not None:
        return blocked
    try:
        body = _parse_json_body(request)
        credential = body.get("credential")
        if not isinstance(credential, dict):
            raise ValueError("Нет данных ключа.")
        device_name = str(body.get("device_name") or "")
        row = complete_registration(
            request,
            credential=credential,
            device_name=device_name,
        )
    except ValueError as exc:
        clear_registration_challenge(request)
        return _json_error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("passkey register complete failed")
        clear_registration_challenge(request)
        return _json_error("Не удалось сохранить ключ доступа.", status=500)
    return JsonResponse(
        {
            "ok": True,
            "id": row.pk,
            "device_name": row.device_name,
            "created_at": row.created_at.isoformat(),
        },
    )


@require_POST
def passkey_login_begin(request: HttpRequest) -> HttpResponse:
    """POST → discoverable PublicKeyCredentialRequestOptions."""
    blocked = _require_enabled()
    if blocked is not None:
        return blocked
    try:
        body = _parse_json_body(request)
    except ValueError as exc:
        return _json_error(str(exc))
    next_url = _safe_next_url(str(body.get("next") or request.GET.get("next") or ""))
    try:
        options = begin_authentication(request, next_url=next_url)
    except Exception:  # noqa: BLE001
        logger.exception("passkey login begin failed")
        return _json_error("Не удалось начать вход по ключу.", status=500)
    return JsonResponse({"ok": True, "publicKey": options})


@require_POST
def passkey_login_complete(request: HttpRequest) -> HttpResponse:
    """POST JSON assertion → session login for staff user."""
    blocked = _require_enabled()
    if blocked is not None:
        return blocked
    try:
        body = _parse_json_body(request)
        credential = body.get("credential")
        if not isinstance(credential, dict):
            raise ValueError("Нет данных ключа.")
        user, next_url = complete_authentication(request, credential=credential)
    except ValueError as exc:
        clear_authentication_challenge(request)
        _record_login_failure(request)
        return _json_error(str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("passkey login complete failed")
        clear_authentication_challenge(request)
        _record_login_failure(request)
        return _json_error("Не удалось войти по ключу доступа.", status=500)

    auth_login(
        request,
        user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    return JsonResponse({"ok": True, "redirect": _safe_next_url(next_url)})


@ensure_csrf_cookie
@require_GET
def passkey_manage_view(request: HttpRequest) -> HttpResponse:
    """Staff page: list own passkeys + register / delete."""
    blocked = _require_enabled() or _require_staff(request)
    if blocked is not None:
        return blocked
    site = admin.site
    target = request.user
    target_id = request.GET.get("user")
    if target_id and request.user.is_superuser:
        from django.contrib.auth import get_user_model

        target = get_object_or_404(get_user_model(), pk=target_id, is_staff=True)

    context = {
        **site.each_context(request),
        "title": "Ключи доступа",
        "passkeys": passkeys_for_user(target),
        "target_user": target,
        "is_own": target.pk == request.user.pk,
        "passkey_register_begin_url": reverse("admin:passkey_register_begin"),
        "passkey_register_complete_url": reverse("admin:passkey_register_complete"),
        "has_permission": True,
    }
    return render(request, "admin/passkeys_manage.html", context)


@require_POST
def passkey_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a passkey (own, or any if superuser)."""
    blocked = _require_enabled() or _require_staff(request)
    if blocked is not None:
        return blocked
    row = get_object_or_404(PasskeyCredential.objects.select_related("user"), pk=pk)
    if row.user_id != request.user.pk and not request.user.is_superuser:
        return _json_error("Недостаточно прав.", status=403)

    wants_json = "application/json" in (request.headers.get("Accept") or "")
    row_user_id = row.user_id
    row.delete()
    if wants_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})

    messages.success(request, "Ключ доступа удалён.")
    manage_url = reverse("admin:passkey_manage")
    if row_user_id != request.user.pk:
        manage_url = f"{manage_url}?user={row_user_id}"
    return redirect(manage_url)


def passkey_login_context(request: HttpRequest) -> dict[str, Any]:
    """Template context bits for Admin login pages."""
    if not admin_passkey_enabled():
        return {"admin_passkey_enabled": False}
    return {
        "admin_passkey_enabled": True,
        "passkey_login_begin_url": reverse("admin:passkey_login_begin"),
        "passkey_login_complete_url": reverse("admin:passkey_login_complete"),
    }


def install_admin_passkeys() -> None:
    """Register passkey routes on the default AdminSite (idempotent)."""
    site = admin.site
    if getattr(site, "_hoocon_admin_passkeys_installed", False):
        return

    original_get_urls = site.get_urls

    def get_urls() -> list[Any]:
        return [
            path(
                "passkey/register/begin/",
                passkey_register_begin,
                name="passkey_register_begin",
            ),
            path(
                "passkey/register/complete/",
                passkey_register_complete,
                name="passkey_register_complete",
            ),
            path(
                "passkey/login/begin/",
                passkey_login_begin,
                name="passkey_login_begin",
            ),
            path(
                "passkey/login/complete/",
                passkey_login_complete,
                name="passkey_login_complete",
            ),
            path("passkey/manage/", passkey_manage_view, name="passkey_manage"),
            path(
                "passkey/<int:pk>/delete/",
                passkey_delete_view,
                name="passkey_delete",
            ),
        ] + original_get_urls()

    site.get_urls = get_urls  # type: ignore[method-assign]
    site._hoocon_admin_passkeys_installed = True  # type: ignore[attr-defined]
    logger.debug("Admin passkeys installed on default AdminSite")
