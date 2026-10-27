"""MAX inbound attachment URL allowlist (SSRF hardening)."""

from __future__ import annotations

from social.max_http import max_attachment_url_allowed
from social.publishers import max_download_attachment


def test_max_attachment_url_allows_cdn_host() -> None:
    assert max_attachment_url_allowed("https://cdn.max.ru/x/pic.jpg") is True


def test_max_attachment_url_blocks_internal_and_evil_hosts() -> None:
    assert max_attachment_url_allowed("http://cdn.max.ru/x") is False
    assert max_attachment_url_allowed("https://127.0.0.1/x") is False
    assert max_attachment_url_allowed("https://hoocon.ru.evil.com/x") is False
    assert max_attachment_url_allowed("file:///etc/passwd") is False


def test_max_download_attachment_refuses_disallowed_url() -> None:
    assert max_download_attachment("https://example.com/payload") is None
