"""TLS contexts for Russian services signed by the Minцифры root CA."""

from __future__ import annotations

import ssl
from pathlib import Path

from django.conf import settings

RUSSIAN_TRUSTED_CA_BUNDLE = Path(settings.BASE_DIR) / "certs" / "max-ca-bundle.pem"


def russian_trusted_ssl_context() -> ssl.SSLContext:
    """Verifying context: public roots (certifi) plus Russian Trusted Root/Sub CA."""
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    if RUSSIAN_TRUSTED_CA_BUNDLE.is_file():
        ctx.load_verify_locations(cafile=str(RUSSIAN_TRUSTED_CA_BUNDLE))
    return ctx
