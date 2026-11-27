"""URLs of the «Мой день» page (mounted before ``admin.site.urls``)."""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from crm import workspace_views

urlpatterns = [
    path("", admin.site.admin_view(workspace_views.workspace_home), name="crm-workspace"),
    path(
        "take-lead/<int:lead_id>/",
        admin.site.admin_view(workspace_views.take_lead),
        name="crm-workspace-take-lead",
    ),
    path(
        "company/<int:company_id>/next-step/",
        admin.site.admin_view(workspace_views.company_next_step),
        name="crm-workspace-company-next-step",
    ),
    path(
        "company/<int:company_id>/note/",
        admin.site.admin_view(workspace_views.company_note),
        name="crm-workspace-company-note",
    ),
    path(
        "company/<int:company_id>/call-result/",
        admin.site.admin_view(workspace_views.company_call_result),
        name="crm-workspace-company-call-result",
    ),
    path(
        "close-lead/<int:lead_id>/",
        admin.site.admin_view(workspace_views.close_lead),
        name="crm-workspace-close-lead",
    ),
    path(
        "person/<int:person_id>/note/",
        admin.site.admin_view(workspace_views.person_note),
        name="crm-workspace-person-note",
    ),
    path(
        "chat/<int:chat_id>/take/",
        admin.site.admin_view(workspace_views.take_chat),
        name="crm-workspace-take-chat",
    ),
    path(
        "chat/<int:chat_id>/close/",
        admin.site.admin_view(workspace_views.close_chat),
        name="crm-workspace-close-chat",
    ),
    path(
        "quote/<int:quote_id>/answer/",
        admin.site.admin_view(workspace_views.quote_answer),
        name="crm-workspace-quote-answer",
    ),
    path(
        "finish-lead/<int:lead_id>/",
        admin.site.admin_view(workspace_views.finish_lead),
        name="crm-workspace-finish-lead",
    ),
    path(
        "finish-call/<int:touch_id>/",
        admin.site.admin_view(workspace_views.finish_call),
        name="crm-workspace-finish-call",
    ),
    path(
        "finish-follow-up/<int:company_id>/",
        admin.site.admin_view(workspace_views.finish_follow_up),
        name="crm-workspace-finish-follow-up",
    ),
]
