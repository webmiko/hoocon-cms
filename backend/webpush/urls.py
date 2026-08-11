"""URL routes for Web Push API."""

from __future__ import annotations

from django.urls import path

from webpush.views import SubscribeView, UnsubscribeView, VapidPublicKeyView

urlpatterns = [
    path("vapid-public-key/", VapidPublicKeyView.as_view(), name="webpush-vapid-public"),
    path("subscribe/", SubscribeView.as_view(), name="webpush-subscribe"),
    path("unsubscribe/", UnsubscribeView.as_view(), name="webpush-unsubscribe"),
]
