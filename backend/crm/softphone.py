"""Browser softphone (UIS WebRTC) for Admin: host window, token, caller lookup.

Звонок живёт в странице, а админка — набор отдельных страниц: встроить телефон
в обычную страницу значит оборвать разговор при первом переходе. Поэтому
телефон — отдельное окно ``/admin/crm/softphone/``; остальные страницы
админки (``hoocon-softphone-dock.js``) говорят с ним через BroadcastChannel.

Токен WebRTC личный: сотруднику отдаётся только его собственный, только
POST-ом с CSRF и без кэша. Журнал звонков по-прежнему пишет вебхук Новосистем
(``crm.novosystem``) — телефон в браузере его не заменяет.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.models import StaffVpbxProfile
from config.unfold_callbacks import _versioned_static
from crm.models import Client
from crm.services import scope_clients_for_manager
from crm.telephony import normalize_phone_digits
from sitesettings.telephony import novosystem_settings

logger = logging.getLogger("hoocon.crm")

_MIN_LOOKUP_DIGITS = 5
# npm @uiscom/uis_webrtc 2.0.2 (ISC), tarball sha512 сверен с реестром npm.
UIS_WEBRTC_LIB = "admin/js/vendor/uis_webrtc-2.0.2.min.js"


def _is_active_staff(user: Any) -> bool:
    """Signed-in, active staff account (the admin login already passed 2FA)."""
    return bool(getattr(user, "is_authenticated", False) and user.is_active and user.is_staff)


def softphone_profile(user: Any) -> StaffVpbxProfile | None:
    """The user's enabled telephony profile with a stored WebRTC token, if any.

    Does not decrypt: cheap enough to run on every admin page render.
    """
    if not _is_active_staff(user):
        return None
    return StaffVpbxProfile.objects.filter(user_id=user.pk, is_enabled=True).exclude(uis_webrtc_token="").first()


def softphone_enabled_for(user: Any) -> bool:
    """True when the Novosystem widget is on and this user has a browser-phone token."""
    if softphone_profile(user) is None:
        return False
    enabled, _token, _virtual, _secret = novosystem_settings()
    return enabled


def softphone_blockers(user: Any) -> list[str]:
    """Reasons the browser phone cannot start for this user (empty = ready)."""
    if not _is_active_staff(user):
        return ["Нужен вход в админку."]
    blockers: list[str] = []
    enabled, _token, _virtual, _secret = novosystem_settings()
    if not enabled:
        blockers.append("Виджет Новосистем выключен: включите его на странице «Интеграции».")
    profile = softphone_profile(user)
    if profile is None:
        blockers.append(
            "Токен WebRTC не задан или профиль выключен: администратор указывает его "
            "в профиле пользователя («Телефония сотрудника»)."
        )
    elif not profile.uis_webrtc_token_plain:
        blockers.append("Сохранённый токен WebRTC не читается: пусть администратор введёт его заново.")
    return blockers


def _forbidden_json(detail: str, **extra: Any) -> JsonResponse:
    return JsonResponse({"detail": detail, **extra}, status=403)


@never_cache
@require_GET
def window_view(request: HttpRequest) -> HttpResponse:
    """The «Телефон» window: UIS WebRTC lives here and survives admin navigation."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), login_url=reverse("admin:login"))
    if not _is_active_staff(request.user):
        raise PermissionDenied
    context = {
        "blockers": softphone_blockers(request.user),
        "session_url": reverse("crm_softphone_session"),
        "lookup_url": reverse("crm_softphone_lookup"),
        "css_url": _versioned_static("admin/css/hoocon-softphone.css"),
        "js_url": _versioned_static("admin/js/hoocon-softphone-window.js"),
        "lib_url": static(UIS_WEBRTC_LIB),
    }
    return render(request, "admin/crm/softphone.html", context)


@never_cache
@require_POST
def session_view(request: HttpRequest) -> JsonResponse:
    """Give the signed-in user their own WebRTC token (never anyone else's)."""
    if not _is_active_staff(request.user):
        return _forbidden_json("Нужен вход в админку.")
    blockers = softphone_blockers(request.user)
    if blockers:
        return _forbidden_json(blockers[0], blockers=blockers)
    profile = softphone_profile(request.user)
    assert profile is not None  # blockers is empty only when a profile exists
    logger.info("softphone_session user=%s", request.user.pk)
    name = (profile.user.first_name or profile.user.email or "").strip()
    return JsonResponse({"token": profile.uis_webrtc_token_plain, "name": name})


@never_cache
@require_GET
def lookup_view(request: HttpRequest) -> JsonResponse:
    """Who is calling: a CRM card by phone, limited to cards this manager may open."""
    if softphone_profile(request.user) is None:
        return _forbidden_json("Телефон в браузере не включён.")
    if not request.user.has_perm("crm.view_client"):
        return _forbidden_json("Нет права просмотра клиентов.")
    digits = normalize_phone_digits(request.GET.get("phone", ""))
    if len(digits) < _MIN_LOOKUP_DIGITS:
        return JsonResponse({"found": False})
    visible = scope_clients_for_manager(Client.objects.filter(is_active=True, phone_digits=digits), request.user)
    client = visible.order_by("id").first()
    if client is None:
        return JsonResponse({"found": False})
    return JsonResponse(
        {
            "found": True,
            "name": client.name or client.email,
            "company": client.company,
            "url": reverse("admin:crm_client_change", args=[client.pk]),
        }
    )
