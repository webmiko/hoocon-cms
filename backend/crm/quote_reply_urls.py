"""Public URLs for the quote reply page (``/api/quotes/reply/``)."""

from __future__ import annotations

from django.urls import path

from crm.quote_reply_views import QuoteReplyView

urlpatterns = [
    path("reply/", QuoteReplyView.as_view(), name="quote-reply"),
]
