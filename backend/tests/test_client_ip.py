"""Client IP behind host nginx: one resolver, spoof-proof X-Forwarded-For."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle

from config.admin_otp import AdminOtpDeliveryError, consume_otp_request_quota
from config.client_ip import client_ip

_NGINX = Path(__file__).resolve().parents[2] / "deploy" / "nginx"
_DOCKER_GATEWAY = "172.18.0.1"


def _request(xff: str = "", remote: str = _DOCKER_GATEWAY):
    meta = {"REMOTE_ADDR": remote}
    if xff:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    return RequestFactory().get("/", **meta)


def test_client_ip_ignores_client_supplied_forwarded_prefix() -> None:
    """Квота OTP брала крайний левый XFF — клиент подставлял любой IP и обходил лимит."""
    assert client_ip(_request("6.6.6.6, 198.51.100.9")) == "198.51.100.9"
    assert client_ip(_request("198.51.100.9")) == "198.51.100.9"


def test_client_ip_falls_back_to_peer_on_garbage_or_no_header() -> None:
    assert client_ip(_request("not-an-ip")) == _DOCKER_GATEWAY
    assert client_ip(_request()) == _DOCKER_GATEWAY
    assert client_ip(_request(remote="")) == "0.0.0.0"


@override_settings(TRUSTED_PROXY_HOPS=0)
def test_client_ip_without_proxy_trusts_only_peer() -> None:
    assert client_ip(_request("198.51.100.9")) == _DOCKER_GATEWAY


def test_drf_throttle_ident_matches_shared_resolver() -> None:
    """DRF без NUM_PROXIES ключевал троттлинг по всей строке XFF — ротация заголовка снимала лимит."""
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == settings.TRUSTED_PROXY_HOPS
    for xff in ("1.1.1.1, 198.51.100.9", "2.2.2.2, 198.51.100.9"):
        ident = AnonRateThrottle().get_ident(Request(_request(xff)))
        assert ident == "198.51.100.9"


def test_otp_quota_cannot_be_bypassed_by_rotating_forwarded_for() -> None:
    cache.clear()
    for n in range(3):
        consume_otp_request_quota(_request(f"10.0.0.{n}, 198.51.100.9"), limit=3, window=60)
    with pytest.raises(AdminOtpDeliveryError):
        consume_otp_request_quota(_request("10.9.9.9, 198.51.100.9"), limit=3, window=60)


def test_axes_uses_shared_client_ip_resolver() -> None:
    """django-ipware не установлен: axes видел IP шлюза Docker и блокировал вход всем сотрудникам."""
    assert settings.AXES_CLIENT_IP_CALLABLE == "config.client_ip.client_ip"


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_axes_lockout_of_one_ip_does_not_block_other_staff() -> None:
    User.objects.create_user(username="editor", password="correct-pass-not-secret", is_staff=True)
    attacker = Client(REMOTE_ADDR=_DOCKER_GATEWAY, HTTP_X_FORWARDED_FOR="203.0.113.66")
    for _ in range(settings.AXES_FAILURE_LIMIT + 1):
        attacker.post("/admin/login/", {"username": "editor", "password": "wrong"})

    colleague = Client(REMOTE_ADDR=_DOCKER_GATEWAY, HTTP_X_FORWARDED_FOR="198.51.100.20")
    response = colleague.post(
        "/admin/login/",
        {"username": "editor", "password": "correct-pass-not-secret", "next": "/admin/"},
    )
    assert response.status_code == 302


def test_nginx_overwrites_forwarded_for_with_peer_address() -> None:
    """$proxy_add_x_forwarded_for сохранял присланный клиентом заголовок."""
    for name in ("hoocon-site.inc", "hoocon-sslip-ssl.conf"):
        text = (_NGINX / name).read_text(encoding="utf-8")
        assert "$proxy_add_x_forwarded_for" not in text, name
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in text, name
