"""URL routes for social integration webhooks."""

from __future__ import annotations

from django.urls import path

from social.views import TelegramWebhookView

urlpatterns = [
    path(
        "telegram/webhook/",
        TelegramWebhookView.as_view(),
        name="telegram-webhook",
    ),
]
