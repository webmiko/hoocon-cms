"""URL routes for ``/api/account/*`` (client cabinet)."""

from __future__ import annotations

from django.urls import path

from cabinet import views

urlpatterns = [
    path("me/", views.AccountMeView.as_view(), name="account-me"),
    path("summary/", views.AccountSummaryView.as_view(), name="account-summary"),
    path("leads/", views.AccountLeadsView.as_view(), name="account-leads"),
    path("leads/<int:pk>/", views.AccountLeadDetailView.as_view(), name="account-lead-detail"),
    path(
        "leads/<int:pk>/repeat/",
        views.AccountLeadRepeatView.as_view(),
        name="account-lead-repeat",
    ),
    path("specs/", views.AccountSpecsView.as_view(), name="account-specs"),
    path("specs/<int:pk>/", views.AccountSpecDetailView.as_view(), name="account-spec-detail"),
    path(
        "specs/<int:pk>/to_lead/",
        views.AccountSpecToLeadView.as_view(),
        name="account-spec-to-lead",
    ),
    path("quotes/", views.AccountQuotesView.as_view(), name="account-quotes"),
    path("quotes/<int:pk>/", views.AccountQuoteDetailView.as_view(), name="account-quote-detail"),
    path(
        "quotes/<int:pk>/pdf/",
        views.AccountQuotePdfView.as_view(),
        name="account-quote-pdf",
    ),
    path("documents/", views.AccountDocumentsView.as_view(), name="account-documents"),
    path(
        "documents/zip/",
        views.AccountDocumentsZipView.as_view(),
        name="account-documents-zip",
    ),
    path(
        "documents/<int:pk>/download/",
        views.AccountDocumentDownloadView.as_view(),
        name="account-document-download",
    ),
    path("orders/", views.AccountOrdersView.as_view(), name="account-orders"),
    path("orders/<int:pk>/", views.AccountOrderDetailView.as_view(), name="account-order-detail"),
    path(
        "conversations/",
        views.AccountConversationsView.as_view(),
        name="account-conversations",
    ),
    path("company/", views.AccountCompanyView.as_view(), name="account-company"),
    path("rma/", views.AccountRmaView.as_view(), name="account-rma"),
    path(
        "rma/<int:pk>/photo/",
        views.AccountRmaPhotoView.as_view(),
        name="account-rma-photo",
    ),
]
