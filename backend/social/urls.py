"""URL routes for social integration webhooks."""

from __future__ import annotations

from django.urls import path

from social.views import MaxWebhookView, TelegramWebhookView, VkCallbackView

urlpatterns = [
    path(
        "telegram/webhook/",
        TelegramWebhookView.as_view(),
        name="telegram-webhook",
    ),
    path(
        "max/webhook/",
        MaxWebhookView.as_view(),
        name="max-webhook",
    ),
    path(
        "vk/callback/",
        VkCallbackView.as_view(),
        name="vk-callback",
    ),
]
