"""GigaChat TLS: certificates are verified by default (M4).

Regression: GIGACHAT_VERIFY_SSL defaulted to false → CERT_NONE, so the
Authorization Key and chat transcripts went over unverified TLS.
"""

from __future__ import annotations

import ssl
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from django.conf import settings as django_settings

from config.tls import RUSSIAN_TRUSTED_CA_BUNDLE
from supportchat.gigachat import client


def test_gigachat_verifies_tls_by_default(monkeypatch: Any, settings: Any) -> None:
    """Без переменной окружения TLS к GigaChat проверяется."""
    from config.settings import _env_bool

    monkeypatch.delenv("GIGACHAT_VERIFY_SSL", raising=False)
    source = (Path(django_settings.BASE_DIR) / "config" / "settings.py").read_text(encoding="utf-8")
    assert 'GIGACHAT_VERIFY_SSL = _env_bool("GIGACHAT_VERIFY_SSL", default=True)' in source
    assert _env_bool("GIGACHAT_VERIFY_SSL", default=True) is True

    settings.GIGACHAT_VERIFY_SSL = True
    ctx = client._ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_gigachat_context_trusts_russian_root_ca(settings: Any) -> None:
    """Сертификат GigaChat подписан Russian Trusted Root CA — он есть в контексте."""
    settings.GIGACHAT_VERIFY_SSL = True
    assert RUSSIAN_TRUSTED_CA_BUNDLE.is_file()
    subjects = {
        dict(item[0] for item in cert["subject"]).get("commonName") for cert in client._ssl_context().get_ca_certs()
    }
    assert "Russian Trusted Root CA" in subjects


def test_post_json_passes_verifying_context(settings: Any) -> None:
    """Запрос к API уходит с проверяющим контекстом, а не context=None/CERT_NONE."""
    settings.GIGACHAT_VERIFY_SSL = True
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b"{}"
    with patch("supportchat.gigachat.client.urllib.request.urlopen", return_value=response) as urlopen:
        client._post_json("https://api.giga.chat/v1/x", headers={})
    ctx = urlopen.call_args.kwargs["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_opt_out_still_possible_for_debugging(settings: Any) -> None:
    settings.GIGACHAT_VERIFY_SSL = False
    assert client._ssl_context().verify_mode == ssl.CERT_NONE
