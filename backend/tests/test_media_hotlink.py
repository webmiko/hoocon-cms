"""Tests for media hotlink Referer allowlist."""

from __future__ import annotations

import pytest
from django.test import override_settings

from config.media_hotlink import (
    build_media_hotlink_hosts,
    host_from_origin_or_url,
    referer_allowed_for_media,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://hoocon.ru/x", "hoocon.ru"),
        ("http://localhost:5173", "localhost"),
        ("hoocon.ru", "hoocon.ru"),
        ("*", None),
        ("", None),
    ],
)
def test_host_from_origin_or_url(value: str, expected: str | None) -> None:
    assert host_from_origin_or_url(value) == expected


def test_build_media_hotlink_hosts_merges_sources() -> None:
    hosts = build_media_hotlink_hosts(
        allowed_hosts=["hoocon.ru", "www.hoocon.ru"],
        cors_origins=["http://localhost:5173"],
        extra_hosts=["staging.hoocon.ru"],
    )
    assert "hoocon.ru" in hosts
    assert "www.hoocon.ru" in hosts
    assert "localhost" in hosts
    assert "staging.hoocon.ru" in hosts


def test_referer_allowed_same_site_and_subdomain() -> None:
    allowed = frozenset({"hoocon.ru", "localhost"})
    assert referer_allowed_for_media(
        "https://hoocon.ru/catalog",
        allowed_hosts=allowed,
        allow_empty=True,
    )
    assert referer_allowed_for_media(
        "https://www.hoocon.ru/",
        allowed_hosts=allowed,
        allow_empty=True,
    )
    assert not referer_allowed_for_media(
        "https://evil.example/page",
        allowed_hosts=allowed,
        allow_empty=True,
    )


def test_referer_empty_policy() -> None:
    allowed = frozenset({"hoocon.ru"})
    assert referer_allowed_for_media(None, allowed_hosts=allowed, allow_empty=True)
    assert not referer_allowed_for_media(None, allowed_hosts=allowed, allow_empty=False)


@override_settings(
    MEDIA_HOTLINK_ENABLED=True,
    MEDIA_HOTLINK_ALLOW_EMPTY_REFERER=True,
    MEDIA_HOTLINK_ALLOWED_HOSTS=frozenset({"hoocon.ru", "localhost", "testserver"}),
    MEDIA_URL="/media/",
)
def test_media_hotlink_middleware_blocks_foreign_referer() -> None:
    from django.http import HttpResponse
    from django.test import RequestFactory

    from config.media_hotlink_middleware import MediaHotlinkMiddleware

    def _ok(_request: object) -> HttpResponse:
        return HttpResponse(b"img", content_type="image/webp")

    middleware = MediaHotlinkMiddleware(_ok)
    factory = RequestFactory()

    allowed = factory.get(
        "/media/product_images/hotlink.webp",
        HTTP_REFERER="https://hoocon.ru/catalog/x",
    )
    assert middleware(allowed).status_code == 200

    blocked = factory.get(
        "/media/product_images/hotlink.webp",
        HTTP_REFERER="https://evil.example/steal",
    )
    assert middleware(blocked).status_code == 403

    direct = factory.get("/media/product_images/hotlink.webp")
    assert middleware(direct).status_code == 200

    other = factory.get("/api/health/", HTTP_REFERER="https://evil.example/")
    assert middleware(other).status_code == 200
