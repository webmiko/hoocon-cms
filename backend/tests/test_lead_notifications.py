"""Tests for new-lead stickers (admin) and email notification prep."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, override_settings

from leads.models import Lead
from leads.services import (
    build_lead_admin_url,
    count_new_leads,
    parse_notify_emails,
    render_lead_notification,
)
from leads.tasks import send_lead_notification

User = get_user_model()

_CSS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css"


def test_parse_notify_emails_splits_and_strips() -> None:
    """Comma/semicolon lists become clean email addresses."""
    assert parse_notify_emails("a@x.ru, b@y.ru;c@z.ru") == [
        "a@x.ru",
        "b@y.ru",
        "c@z.ru",
    ]
    assert parse_notify_emails("  ") == []


@pytest.mark.django_db
def test_count_new_leads_only_unread_status_new() -> None:
    """Badge counts only status=new with seen_at empty."""
    Lead.objects.create(
        name="A",
        email="a@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    Lead.objects.create(
        name="B",
        email="b@example.com",
        message="y" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
    )
    seen = Lead.objects.create(
        name="C",
        email="c@example.com",
        message="z" * 20,
        status=Lead.LeadStatus.NEW,
    )
    from django.utils import timezone

    Lead.objects.filter(pk=seen.pk).update(seen_at=timezone.now())
    assert count_new_leads() == 1


@pytest.mark.django_db
def test_opening_lead_marks_seen_and_drops_sticker_count() -> None:
    """GET change form sets seen_at; sticker count becomes 0; status stays new."""
    lead = Lead.objects.create(
        name="Open Me",
        email="open@example.com",
        message="Откройте эту заявку в админке.",
        status=Lead.LeadStatus.NEW,
    )
    assert count_new_leads() == 1
    admin_user = User.objects.create_superuser(
        username="lead-open",
        email="lead-open@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get(f"/admin/leads/lead/{lead.pk}/change/")
    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.seen_at is not None
    assert lead.status == Lead.LeadStatus.NEW
    assert count_new_leads() == 0


@pytest.mark.django_db
def test_lead_changelist_has_open_button_and_new_badge() -> None:
    """Changelist renders status tag and Открыть button; new leads first."""
    older_new = Lead.objects.create(
        name="Older New",
        email="older@example.com",
        message="Старая новая заявка.",
        status=Lead.LeadStatus.NEW,
    )
    in_progress = Lead.objects.create(
        name="In Progress",
        email="prog@example.com",
        message="Уже в работе.",
        status=Lead.LeadStatus.IN_PROGRESS,
    )
    newer_new = Lead.objects.create(
        name="Newer New",
        email="newer@example.com",
        message="Свежая новая заявка.",
        status=Lead.LeadStatus.NEW,
    )
    admin_user = User.objects.create_superuser(
        username="lead-list",
        email="lead-list@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/leads/lead/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-lead-status--new" in html
    assert "hoocon-admin-lead-open" in html
    assert "Открыть" in html
    # New leads before in_progress; among new — newer first.
    pos_newer = html.find("Newer New")
    pos_older = html.find("Older New")
    pos_prog = html.find("In Progress")
    assert pos_newer != -1 and pos_older != -1 and pos_prog != -1
    assert pos_newer < pos_older < pos_prog
    assert older_new.pk and newer_new.pk and in_progress.pk


@override_settings(SITE_URL="https://hoocon.ru")
def test_build_lead_admin_url_is_absolute() -> None:
    """Manager email links use SITE_URL + admin change path."""
    url = build_lead_admin_url(42)
    assert url == "https://hoocon.ru/admin/leads/lead/42/change/"


@pytest.mark.django_db
@override_settings(SITE_URL="https://hoocon.ru")
def test_render_lead_notification_includes_admin_link() -> None:
    """Plain and HTML bodies include absolute Admin URL for the lead."""
    lead = Lead.objects.create(
        name="Petr",
        email="petr@example.com",
        message="Нужен привод для вентиляции.",
        lead_type=Lead.LeadType.RFQ,
    )
    subject, text_body, html_body = render_lead_notification(lead)
    assert "Petr" in subject
    assert "https://hoocon.ru/admin/leads/lead/" in text_body
    assert f"/admin/leads/lead/{lead.pk}/change/" in text_body
    assert "<html" in html_body.lower() or "<p" in html_body.lower()
    assert f"/admin/leads/lead/{lead.pk}/change/" in html_body


@pytest.mark.django_db
def test_send_lead_notification_html_and_multi_recipients() -> None:
    """Task sends multipart mail to all LEAD_NOTIFY_EMAIL addresses."""
    lead = Lead.objects.create(
        name="Anna",
        email="anna@example.com",
        message="Консультация по подбору.",
        lead_type=Lead.LeadType.CONSULTATION,
    )
    mail.outbox.clear()
    with override_settings(
        LEAD_NOTIFY_EMAIL="sales@hoocon.ru, desk@hoocon.ru",
        SITE_URL="https://hoocon.ru",
        DEFAULT_FROM_EMAIL="noreply@hoocon.ru",
    ):
        send_lead_notification.apply(args=[lead.pk]).get()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert set(msg.to) == {"sales@hoocon.ru", "desk@hoocon.ru"}
    assert msg.alternatives
    html = msg.alternatives[0][0]
    assert "Anna" in html
    assert "text/html" in msg.alternatives[0][1]


@pytest.mark.django_db
def test_admin_index_shows_lead_sticker_when_new_exists() -> None:
    """Staff admin chrome includes new-leads sticker with count."""
    Lead.objects.create(
        name="Sticker",
        email="sticker@example.com",
        message="Нужен КП на приводы.",
        status=Lead.LeadStatus.NEW,
    )
    admin_user = User.objects.create_superuser(
        username="lead-sticker",
        email="lead-sticker@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-admin-lead-sticker" in html
    assert "data-hoocon-new-leads-count" in html
    assert "status__exact=new" in html
    assert "seen_at__isempty=1" in html


@pytest.mark.django_db
def test_new_leads_count_endpoint_requires_staff() -> None:
    """JSON count endpoint is staff-only; returns new lead count."""
    Lead.objects.create(
        name="Count",
        email="count@example.com",
        message="Проверка счётчика заявок.",
        status=Lead.LeadStatus.NEW,
    )
    anon = Client()
    assert anon.get("/admin/leads/lead/new-count/").status_code in {302, 403}

    admin_user = User.objects.create_superuser(
        username="lead-count",
        email="lead-count@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/leads/lead/new-count/")
    assert response.status_code == 200
    assert response.json() == {"count": 1}


@pytest.mark.django_db
def test_new_lead_creates_crm_inbound_activity() -> None:
    """New Lead creates CRM Activity of type note (inbound sticker trail)."""
    from crm.models import Activity, ActivityType

    lead = Lead.objects.create(
        name="CRM Act",
        email="crm-act@example.com",
        message="Заявка для активности CRM.",
    )
    lead.refresh_from_db()
    assert lead.client_id is not None
    activity = Activity.objects.filter(lead=lead, client_id=lead.client_id).first()
    assert activity is not None
    assert activity.activity_type == ActivityType.NOTE
    assert "заявк" in activity.subject.lower()


def test_admin_css_defines_lead_sticker() -> None:
    """Theme CSS includes lead sticker, status tag, and open button."""
    css = _CSS.read_text(encoding="utf-8")
    assert ".hoocon-admin-lead-sticker" in css
    assert "hoocon-admin-lead-sticker__count" in css
    assert ".hoocon-lead-status--new" in css
    assert "a.hoocon-admin-lead-open" in css
