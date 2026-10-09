"""Open-redirect guard: ``/\\evil.com`` passed the old ``startswith("//")`` checks."""

from __future__ import annotations

import pytest

from accounts.passkey_views import _safe_next_url
from config.safe_paths import is_same_site_path, safe_same_site_path
from webpush.services import sanitize_push_url

OFFSITE = ["/\\evil.com", "/\\/evil.com", "/\t/evil.com", "//evil.com", "https://evil.com", "evil.com"]


@pytest.mark.parametrize("raw", OFFSITE)
def test_offsite_targets_rejected_everywhere(raw: str) -> None:
    """Passkey next and push URL fell back only for ``//`` / ``://`` — browsers read ``/\\`` as ``//``."""
    assert not is_same_site_path(raw)
    assert _safe_next_url(raw) == "/admin/"
    assert sanitize_push_url(raw) == "/"


def test_same_site_paths_kept() -> None:
    assert _safe_next_url("/admin/leads/?q=1") == "/admin/leads/?q=1"
    assert sanitize_push_url("/account/leads#top") == "/account/leads#top"
    assert safe_same_site_path("", fallback="/x") == "/x"
    assert len(safe_same_site_path("/" + "a" * 900)) == 500
