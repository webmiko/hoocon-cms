"""Lead board: a site form, an answered call, and a missed call are different chips."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from django.utils import timezone

from crm.models import Call, CallDirection, CallState, Client
from leads.channel import (
    format_temporary_call_name,
    latest_lead_call,
    lead_channel,
    name_is_call_placeholder,
    phone_label_for_lead,
    remember_temporary_call_name,
    temporary_call_name,
)
from leads.models import Lead

User = get_user_model()
_EXTRAS_CSS = Path(__file__).resolve().parents[1] / "static" / "admin" / "css" / "hoocon-unfold-extras.css"


def _row(html: str, marker: str) -> str:
    start = html.find(marker)
    assert start != -1, marker
    tr_start = html.rfind("<tr", 0, start)
    tr_end = html.find("</tr>", start)
    return html[tr_start:tr_end]


def _call(
    *,
    entry_id: str,
    lead: Lead,
    client: Client,
    talk: int,
    started_at: Any,
    connected: bool = False,
) -> Call:
    return Call.objects.create(
        entry_id=entry_id,
        direction=CallDirection.INBOUND,
        state=CallState.DISCONNECTED,
        from_number="79001112233",
        to_number="78003505898",
        client=client,
        lead=lead,
        talk_duration=talk,
        started_at=started_at,
        connected_at=started_at if connected else None,
        finished_at=started_at + timedelta(seconds=max(talk, 1)),
    )


@pytest.mark.django_db
def test_latest_call_decides_whether_the_lead_was_answered() -> None:
    """Два звонка на одной заявке: метка берётся из последнего, разговор > 0 или момент соединения — принят."""
    client = Client.objects.create(email="79001112233@call.invalid", name="+7 900 111-22-33", phone="79001112233")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name=client.name,
        email=client.email,
        phone=client.phone,
        message="Звонок с номера, которого не было в CRM.",
        client=client,
        status=Lead.LeadStatus.NEW,
    )
    now = timezone.now()
    _call(entry_id="uis:old-talk", lead=lead, client=client, talk=40, started_at=now - timedelta(hours=2))
    _call(entry_id="uis:new-miss", lead=lead, client=client, talk=0, started_at=now - timedelta(minutes=5))
    assert lead_channel(lead).call == "missed"
    assert lead_channel(lead).site is False

    _call(entry_id="uis:newest-talk", lead=lead, client=client, talk=15, started_at=now)
    assert lead_channel(lead).call == "answered"

    quiet = Client.objects.create(email="79002223344@call.invalid", name="+7 900 222-33-44", phone="79002223344")
    quiet_lead = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name=quiet.name,
        email=quiet.email,
        phone=quiet.phone,
        message="Звонок с номера, которого не было в CRM.",
        client=quiet,
    )
    _call(
        entry_id="uis:connected-only",
        lead=quiet_lead,
        client=quiet,
        talk=0,
        started_at=now,
        connected=True,
    )
    assert lead_channel(quiet_lead).call == "answered"


@pytest.mark.django_db
def test_lead_changelist_marks_site_form_and_call_outcome() -> None:
    """Стена заявок: форма сайта, пропущенный и принятый звонок — разные метки и цвета."""
    site_client = Client.objects.create(email="buyer@acme.test", name="Покупатель", phone="79007654321")
    site = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Заявка с сайта",
        email=site_client.email,
        phone=site_client.phone,
        company="Акме",
        message="Нужно коммерческое предложение на приводы.",
        client=site_client,
    )
    missed_client = Client.objects.create(
        email="79872857701@call.invalid",
        name="+7 987 285-77-01",
        phone="79872857701",
    )
    missed = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name=missed_client.name,
        email=missed_client.email,
        phone=missed_client.phone,
        message="Звонок с номера, которого не было в CRM.",
        client=missed_client,
    )
    answered_client = Client.objects.create(
        email="79107600012@call.invalid",
        name="+7 910 760-00-12",
        phone="79107600012",
    )
    answered = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name=answered_client.name,
        email=answered_client.email,
        phone=answered_client.phone,
        message="Звонок с номера, которого не было в CRM.",
        client=answered_client,
    )
    followed_client = Client.objects.create(email="office@acme.test", name="Офис", phone="74952293903")
    followed = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name="Форма и потом звонок",
        email=followed_client.email,
        phone=followed_client.phone,
        company="Акме",
        message="Вопрос с формы, затем перезвонили.",
        client=followed_client,
    )
    now = timezone.now()
    _call(entry_id="uis:missed", lead=missed, client=missed_client, talk=0, started_at=now)
    _call(entry_id="uis:answered", lead=answered, client=answered_client, talk=90, started_at=now)
    _call(entry_id="uis:follow", lead=followed, client=followed_client, talk=20, started_at=now)

    admin_user = User.objects.create_superuser(username="lead-channel", email="lead-channel@example.com", password="x")
    http = DjangoClient()
    http.force_login(admin_user)
    html = http.get("/admin/leads/lead/").content.decode()

    site_row = _row(html, "Заявка с сайта")
    assert "Форма сайта" in site_row
    assert "hoocon-lead-origin--site" in site_row
    assert "Звонок принят" not in site_row
    assert "Звонок пропущен" not in site_row
    assert "Заведите карточку клиента" not in site_row

    missed_title = f"Звонок пропущен · +7 987 285-77-01 · {timezone.localtime(now):%d.%m %H:%M}"
    answered_title = f"Звонок принят · +7 910 760-00-12 · {timezone.localtime(now):%d.%m %H:%M}"
    assert missed_title != answered_title
    missed_row = _row(html, missed_title)
    # The title is the temporary name once. The name column is the phone:
    # a ModelAdmin method called ``name`` is skipped, because ``name`` is a field.
    assert missed_row.count(missed_title) == 1
    assert 'class="field-contact_name"' in missed_row or "field-contact_name" in missed_row
    assert missed_row.count("+7 987 285-77-01") == 2
    assert "hoocon-lead-origin--missed" in missed_row
    assert "Звонок принят" not in missed_row
    assert "Форма сайта" not in missed_row
    assert "Звонок, карточка не заведена" not in missed_row
    assert "@call.invalid" not in missed_row
    assert "Заведите карточку клиента и заметку о звонке" in missed_row
    assert f"/admin/crm/client/{missed_client.pk}/change/" in missed_row

    answered_row = _row(html, answered_title)
    assert "hoocon-lead-origin--answered" in answered_row
    assert "Звонок пропущен" not in answered_row
    assert "Форма сайта" not in answered_row

    followed_row = _row(html, "Форма и потом звонок")
    assert "Форма сайта" in followed_row
    assert "Звонок принят" in followed_row
    assert "hoocon-lead-origin--answered" in followed_row

    page = http.get(f"/admin/leads/lead/{missed.pk}/change/").content.decode()
    assert "Это звонок, а не форма с сайта" in page
    assert "Карточка клиента ещё не заведена" in page
    assert "Открыть карточку клиента" in page
    assert f"/admin/crm/client/{missed_client.pk}/change/" in page
    assert "Карточка клиента ещё не заполнена" in page
    assert "Ответить клиенту" not in page

    site_page = http.get(f"/admin/leads/lead/{site.pk}/change/").content.decode()
    assert "Ответить клиенту" in site_page
    assert "Это звонок, а не форма с сайта" not in site_page


@pytest.mark.django_db
def test_finished_unknown_call_stores_a_temporary_name_and_keeps_a_real_one() -> None:
    """Незнакомый номер получает имя с итогом, телефоном и временем. Настоящее имя повтор не затирает."""
    from accounts.models import StaffVpbxProfile
    from crm.novosystem import handle_novosystem_event
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_enabled = True
    site.novosystem_webhook_secret = "hook-secret"
    site.novosystem_access_token = "uis-token"
    site.novosystem_virtual_phone = "74951234567"
    site.save()
    manager = User.objects.create_user(username="name-mgr", email="name-mgr@hoocon.test", is_staff=True)
    StaffVpbxProfile.objects.create(user=manager, uis_employee_id="55", extension="201")

    handle_novosystem_event(
        {
            "id": "miss-a",
            "direction": "in",
            "contact_phone_number": "79872857701",
            "employee_id": "55",
            "start_time": "2026-10-15T16:16:00+03:00",
            "finish_time": "2026-10-15T16:16:20+03:00",
            "talk_duration": "0",
        },
    )
    handle_novosystem_event(
        {
            "id": "talk-b",
            "direction": "in",
            "contact_phone_number": "79107600012",
            "employee_id": "55",
            "start_time": "2026-10-15T16:15:00+03:00",
            "finish_time": "2026-10-15T16:17:00+03:00",
            "talk_duration": "40",
        },
    )
    missed = Lead.objects.get(email="79872857701@call.invalid")
    answered = Lead.objects.get(email="79107600012@call.invalid")
    assert missed.name == "Звонок пропущен · +7 987 285-77-01 · 15.10 16:16"
    assert answered.name == "Звонок принят · +7 910 760-00-12 · 15.10 16:15"
    assert missed.name != answered.name
    assert missed.client is not None and missed.client.name == missed.name

    missed.name = "Иван Петров"
    missed.save(update_fields=["name", "updated_at"])
    missed.client.name = "Иван Петров"
    missed.client.save(update_fields=["name", "updated_at"])
    handle_novosystem_event(
        {
            "id": "miss-a-again",
            "direction": "in",
            "contact_phone_number": "79872857701",
            "employee_id": "55",
            "start_time": "2026-10-15T18:00:00+03:00",
            "finish_time": "2026-10-15T18:00:10+03:00",
            "talk_duration": "0",
        },
    )
    missed.refresh_from_db()
    missed.client.refresh_from_db()
    assert missed.name == "Иван Петров"
    assert missed.client.name == "Иван Петров"


@pytest.mark.django_db
def test_stub_without_a_call_is_still_a_missed_call() -> None:
    """Заявка-заглушка без строки звонка не становится формой сайта и не получает время в имени."""
    lead = Lead(
        email="79870001122@call.invalid",
        phone="",
        name="79870001122",
    )
    assert latest_lead_call(lead) is None
    assert phone_label_for_lead(lead) == "+7 987 000-11-22"
    assert name_is_call_placeholder(lead.name, "+7 987 000-11-22") is True
    assert name_is_call_placeholder("Иван Петров", "+7 987 000-11-22") is False
    assert format_temporary_call_name(phone_label="+7 987 000-11-22", answered=False, when=None) == (
        "Звонок пропущен · +7 987 000-11-22"
    )
    channel = lead_channel(lead)
    assert channel.site is False
    assert channel.call == "missed"
    assert channel.stub is True
    assert temporary_call_name(lead) == "Звонок пропущен · +7 987 000-11-22"

    blank = Lead(email="office@acme.test", phone="123", name="")
    assert phone_label_for_lead(blank) == "без номера"
    assert name_is_call_placeholder("", "без номера") is True
    assert lead_channel(blank).call is None
    assert lead_channel(blank).site is True

    saved = Client.objects.create(email="buyer@acme.test", name="Покупатель", phone="79001112233")
    call = Call.objects.create(entry_id="uis:not-a-stub", from_number="79001112233", client=saved)
    remember_temporary_call_name(call)
    saved.refresh_from_db()
    assert saved.name == "Покупатель"
    orphan = Call.objects.create(entry_id="uis:no-client", from_number="79001112233")
    remember_temporary_call_name(orphan)


def test_call_origin_chips_use_different_colors_in_loaded_admin_css() -> None:
    """Unfold грузит hoocon-unfold-extras.css: пропущенный красный, принятый зелёный, форма синяя."""
    css = _EXTRAS_CSS.read_text(encoding="utf-8")
    missed = css.split(".hoocon-lead-origin--missed {", 1)[1].split("}", 1)[0]
    answered = css.split(".hoocon-lead-origin--answered {", 1)[1].split("}", 1)[0]
    site = css.split(".hoocon-lead-origin--site {", 1)[1].split("}", 1)[0]
    assert "#991b1b" in missed and "#dc2626" in missed
    assert "#166534" in answered and "#16a34a" in answered
    assert "#1e3a8a" in site and "#2563eb" in site
    assert missed != answered
