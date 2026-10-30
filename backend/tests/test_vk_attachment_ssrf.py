"""VK inbound attachment URL allowlist (SSRF hardening)."""

from __future__ import annotations

from social.vk_http import vk_attachment_url_allowed, vk_download_attachment


def test_vk_attachment_url_allows_userapi_cdn() -> None:
    assert vk_attachment_url_allowed("https://sun9-1.userapi.com/impg/abc.jpg") is True


def test_vk_attachment_url_blocks_internal_and_evil_hosts() -> None:
    assert vk_attachment_url_allowed("http://sun9-1.userapi.com/x") is False
    assert vk_attachment_url_allowed("https://127.0.0.1/x") is False
    assert vk_attachment_url_allowed("https://userapi.com.evil.net/x") is False
    assert vk_attachment_url_allowed("file:///etc/passwd") is False


def test_vk_download_attachment_refuses_disallowed_url() -> None:
    assert vk_download_attachment("https://example.com/payload") is None


def test_vk_download_attachment_fetches_allowed_cdn() -> None:
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"img-bytes"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    url = "https://sun9-1.userapi.com/impg/x.jpg"
    with patch("social.vk_http.public_urlopen", return_value=mock_resp):
        got = vk_download_attachment(url)
    assert got == (b"img-bytes", "x.jpg")
