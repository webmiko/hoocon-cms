"""URL routes for public support chat API."""

from __future__ import annotations

from django.urls import path

from supportchat.views import (
    ConversationStartView,
    CurrentMessagesView,
    SupportChannelsView,
    SupportScheduleView,
)

urlpatterns = [
    path("schedule/", SupportScheduleView.as_view(), name="support-schedule"),
    path("channels/", SupportChannelsView.as_view(), name="support-channels"),
    path(
        "conversations/",
        ConversationStartView.as_view(),
        name="support-conversation-start",
    ),
    path(
        "conversations/current/messages/",
        CurrentMessagesView.as_view(),
        name="support-current-messages",
    ),
]
