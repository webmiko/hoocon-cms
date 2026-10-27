"""One blank tabular row when the parent card has no lines yet."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client as DjangoClient
from django.test import RequestFactory
from django.urls import reverse

from crm.admin.inlines import (
    ActivityInline,
    ClientDocumentInline,
    LeadInline,
    OrderInline,
    QuoteInline,
)
from crm.models import Client


@pytest.mark.django_db
def test_one_blank_row_resolves_fk_without_explicit_fk_name() -> None:
    """Mixin must not rely on InlineModelAdmin.fk_name (usually None on the instance)."""
    person = Client.objects.create(name="Тест", email="inline-fk@test.local", company="")
    request = RequestFactory().get("/")
    request.user = User.objects.create_superuser("inline-fk", "inline-fk@test.local", "x")
    cases = (
        (LeadInline, "leads"),
        (ActivityInline, "activities"),
        (QuoteInline, "quotes"),
        (OrderInline, "orders"),
        (ClientDocumentInline, "documents"),
    )
    for inline_class, prefix in cases:
        inline = inline_class(Client, admin.site)
        assert inline.has_add_permission(request, person)
        assert inline.get_extra(request, person) == 1, prefix
        formset = inline.get_formset(request, person)(instance=person)
        assert formset.total_form_count() == 1, prefix
        assert formset.forms[0].prefix == f"{prefix}-0", prefix


@pytest.mark.django_db
def test_empty_client_card_renders_visible_blank_inlines() -> None:
    """КП, заказ, документ, лид, активность — одна строка без клика «Добавить»."""
    admin_user = User.objects.create_superuser("card-blank", "card-blank@test.local", "x")
    person = Client.objects.create(name="Пустая", email="blank-card@test.local", company="")
    page = DjangoClient()
    page.force_login(admin_user)
    html = page.get(reverse("admin:crm_client_change", args=[person.pk])).content.decode()
    for field_name in (
        "leads-0-message",
        "activities-0-subject",
        "quotes-0-comment",
        "orders-0-number",
        "documents-0-title",
    ):
        assert f'name="{field_name}"' in html, field_name
