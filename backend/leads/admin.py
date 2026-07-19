"""Admin registration for leads.Lead (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead; docs/readiness-backend-ux.md §2.2.
Staff manages leads via Django Admin: read/edit status, view PII in admin
context only (PII never exposed in public API — Slice 19).
"""

from __future__ import annotations

from django.contrib import admin

from leads.models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    """Admin for customer inquiries (RFQ / consultation / replacement).

    PII (email/phone) is visible to staff in Admin — that's the only
    place where full contact data is exposed. Public API (Slice 19)
    never returns email/phone in the response.
    """

    list_display = (
        "id",
        "lead_type",
        "name",
        "company",
        "status",
        "created_at",
    )
    list_filter = ("lead_type", "status", "created_at")
    search_fields = ("name", "company", "email", "message", "analog_belimo_code")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    # Staff edits status; PII fields are editable for follow-up notes.
    fieldsets = (
        (
            "Тип заявки",
            {
                "fields": ("lead_type", "status", "sku", "quantity", "analog_belimo_code"),
            },
        ),
        (
            "Контакт",
            {
                "fields": ("name", "email", "phone", "company"),
            },
        ),
        (
            "Сообщение",
            {
                "fields": ("message",),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
