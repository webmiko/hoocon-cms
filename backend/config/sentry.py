"""Optional Sentry error tracking (enabled when SENTRY_DSN is set)."""

from __future__ import annotations

import os

from config.release import package_version


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    return default


def init_sentry() -> None:
    """Initialize Sentry SDK for Django + Celery when DSN is configured."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    debug = _env_bool("DJANGO_DEBUG", default=False)
    environment = os.getenv("SENTRY_ENVIRONMENT", "").strip() or ("development" if debug else "production")
    release = os.getenv("SENTRY_RELEASE", "").strip() or f"hoocon-cms@{package_version()}"
    traces_raw = os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0").strip() or "0"
    try:
        traces_sample_rate = float(traces_raw)
    except ValueError:
        traces_sample_rate = 0.0

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )
