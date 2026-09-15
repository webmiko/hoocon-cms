"""DRF auth + permissions for staff mobile API."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from staff_api.models import StaffAuthToken
from staff_api.tokens import lookup_staff_token, touch_staff_token_last_used


class StaffTokenAuthentication(BaseAuthentication):
    """``Authorization: Token <key>`` for staff mobile clients."""

    keyword = b"token"

    def authenticate(self, request: Request) -> tuple[AbstractBaseUser, StaffAuthToken] | None:
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None
        if len(auth) != 2:
            raise AuthenticationFailed("Некорректный заголовок Authorization.")
        raw = auth[1].decode("utf-8")
        token = lookup_staff_token(raw)
        if token is None:
            raise AuthenticationFailed("Недействительный токен.")
        user = token.user
        if not user.is_active or not user.is_staff:
            raise AuthenticationFailed("Учётная запись недоступна.")
        touch_staff_token_last_used(token)
        return user, token


class IsStaffManager(BasePermission):
    """Active staff in groups Менеджер or Админ (or superuser)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not user.is_active or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        names = set(user.groups.values_list("name", flat=True))
        return GROUP_MANAGER in names or GROUP_ADMIN in names
