"""Company phones: one row per number, and a call on any of them finds the company."""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import StaffVpbxProfile
from crm.models import Client, Company
from crm.phones import company_for_phone, split_phone_numbers
from crm.telephony import normalize_phone_digits
from sitesettings.models import SiteSettings

RAW = "+7 (843) 554-00-45; +7 (843) 555-53-96; +7 (843) 214-08-85"
SECOND = "+7 (843) 555-53-96"


def test_several_numbers_in_one_cell_stay_separate() -> None:
    """The softphone rejects a number longer than 15 digits, so the cell must be split."""
    assert len(re.sub(r"\D", "", RAW)) > 15
    numbers = split_phone_numbers(RAW)
    assert numbers == [
        "+7 (843) 554-00-45",
        "+7 (843) 555-53-96",
        "+7 (843) 214-08-85",
    ]
    assert [normalize_phone_digits(number) for number in numbers] == [
        "78435540045",
        "78435555396",
        "78432140885",
    ]


@pytest.mark.django_db
def test_company_change_shows_one_input_per_number(client: Any) -> None:
    """The company form lists each number, a call link, and a button to add another."""
    from pathlib import Path

    user = get_user_model().objects.create_superuser("phones-admin", "phones-admin@example.com", "password12")
    org = Company.objects.create(name="ООО «Три номера»", phone=RAW)
    client.force_login(user)
    response = client.get(reverse("admin:crm_company_change", args=[org.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count('name="phone"') == 3
    assert "Добавить телефон" in html
    assert "hoocon-company-phones.js" in html
    assert 'href="tel:+78435555396"' in html
    assert "Плановые звонки" in html
    assert "Контакты" in html
    css = Path("static/admin/css/hoocon-unfold-extras.css").read_text(encoding="utf-8")
    assert ".hoocon-phones" in css
    assert "flex-direction: column" in css


@pytest.mark.django_db
def test_incoming_call_on_the_second_number_opens_that_company(django_user_model: Any) -> None:
    """A call to a number that is not the first one still belongs to this company."""
    from crm.novosystem import handle_novosystem_event

    site = SiteSettings.load()
    site.novosystem_enabled = True
    site.novosystem_webhook_secret = "hook-secret"
    site.novosystem_access_token = "uis-token"
    site.novosystem_virtual_phone = "74951234567"
    site.save()
    manager = django_user_model.objects.create_user(
        username="phones-mgr",
        email="phones-mgr@example.com",
        is_staff=True,
    )
    StaffVpbxProfile.objects.create(user=manager, uis_employee_id="55", extension="201")
    org = Company.objects.create(name="ООО «Три номера»", phone=RAW)
    assert company_for_phone(SECOND).pk == org.pk
    assert company_for_phone("+7 (843) 000-00-00") is None

    with (
        patch("leads.tasks.send_lead_notification.delay"),
        patch("leads.tasks.send_lead_client_confirmation.delay"),
    ):
        assert (
            handle_novosystem_event(
                {
                    "id": "second-number",
                    "direction": "in",
                    "contact_phone_number": "78435555396",
                    "employee_id": "55",
                    "finish_time": "2026-10-21T16:00:00+03:00",
                },
            )
            == "created"
        )

    stub = Client.objects.get(email="78435555396@call.invalid")
    assert stub.company_ref_id == org.pk
    assert Client.objects.filter(company_ref=org).count() == 1


def test_phone_list_drops_duplicates_and_russian_notes() -> None:
    """A repeated number and a parenthetical note do not become extra phones."""
    from crm.phones import join_phone_numbers

    joined = join_phone_numbers(
        "+7 (843) 554-00-45, +7 (843) 554-00-45 (актуально по сайту)",
        "+7 (843) 555-53-96",
    )
    assert joined == "+7 (843) 554-00-45; +7 (843) 555-53-96"


def test_phone_widget_reads_a_list_or_a_single_value() -> None:
    """The company form posts one input per number and stores them together."""
    from django.http import QueryDict

    from crm.phone_widget import MultiPhoneWidget

    widget = MultiPhoneWidget()
    posted = QueryDict(mutable=True)
    posted.setlist("phone", ["+7 (843) 554-00-45", "", "+7 (843) 554-00-45"])
    assert widget.value_from_datadict(posted, None, "phone") == "+7 (843) 554-00-45"
    assert widget.value_from_datadict({"phone": "+7 (843) 214-08-85"}, None, "phone") == "+7 (843) 214-08-85"
    rows = widget.get_context("phone", "12345", {})["rows"]
    assert rows[0]["tel"] == ""


@pytest.mark.django_db
def test_saving_the_company_replaces_indexed_numbers() -> None:
    """Editing the phone list drops the old index and rewrites the same digits."""
    from types import SimpleNamespace

    from crm.phones import sync_company_phones

    sync_company_phones(SimpleNamespace(phone="+7 (843) 554-00-45"))
    org = Company.objects.create(name="Синхронизация", phone="+7 (843) 554-00-45")
    org.phone = "+7 843 554-00-45; +7 (843) 555-53-96"
    org.save()
    assert list(org.phones.order_by("sort").values_list("number", "phone_digits")) == [
        ("+7 843 554-00-45", "78435540045"),
        ("+7 (843) 555-53-96", "78435555396"),
    ]


@pytest.mark.django_db
def test_company_and_call_actions_assign_and_merge(client: Any) -> None:
    """Changelist actions require change permission and actually set the manager."""
    from django.contrib.admin.sites import site
    from django.test import RequestFactory
    from django.utils import timezone

    from crm.models import PlannedTouch

    admin = get_user_model().objects.create_superuser("act-admin", "act-admin@example.com", "password12")
    client.force_login(admin)
    org = Company.objects.create(name="Без менеджера")
    other = Company.objects.create(name="Вторая")
    alone = client.post(
        reverse("admin:crm_company_changelist"),
        {"action": "merge_companies_action", "_selected_action": [str(org.pk)]},
    )
    assert alone.status_code == 302
    taken = client.post(
        reverse("admin:crm_company_changelist"),
        {"action": "assign_to_me", "_selected_action": [str(org.pk)]},
    )
    assert taken.status_code == 302
    org.refresh_from_db()
    assert org.assignee_id == admin.pk
    merged = client.post(
        reverse("admin:crm_company_changelist"),
        {"action": "merge_companies_action", "_selected_action": [str(org.pk), str(other.pk)]},
    )
    assert merged.status_code == 302
    assert not Company.objects.filter(pk=other.pk).exists()

    touch = PlannedTouch.objects.create(
        company=org,
        starts_at=timezone.now(),
        title="Звонок",
        dedupe_key="action-touch",
    )
    called = client.post(
        reverse("admin:crm_plannedtouch_changelist"),
        {"action": "assign_to_me", "_selected_action": [str(touch.pk)]},
    )
    assert called.status_code == 302
    touch.refresh_from_db()
    assert touch.assignee_id == admin.pk

    model_admin = site._registry[PlannedTouch]
    request = RequestFactory().post("/admin/")
    request.user = admin
    fresh = PlannedTouch(company=org, starts_at=timezone.now(), title="Новый")
    model_admin.save_model(request, fresh, None, False)
    assert fresh.pk
    assert fresh.dedupe_key.startswith(f"company:{org.pk}:")
    again = PlannedTouch(company=org, starts_at=fresh.starts_at, title="Повтор")
    model_admin.save_model(request, again, None, False)
    assert again.dedupe_key != fresh.dedupe_key
    loose = PlannedTouch(starts_at=timezone.now(), title="Без компании")
    model_admin.save_model(request, loose, None, False)
    assert loose.dedupe_key.startswith("manual:")


@pytest.mark.django_db
def test_company_card_gives_each_new_planned_call_its_own_key(client: Any) -> None:
    """Two calls added on the company card both save, and the workbook day key is taken.

    The inline does not run PlannedTouchAdmin.save_model. An empty dedupe_key
    made the second insert hit the unique constraint and let a later file
    create the same company-day again.
    """
    from datetime import datetime

    from django.utils import timezone

    from crm.models import PlannedTouch
    from crm.outreach import touch_dedupe_key
    from tests.test_admin_scope_hardening import _admin_change_post

    user = get_user_model().objects.create_superuser("call-key", "call-key@example.com", "password12")
    org = Company.objects.create(name="Карточка звонков")
    client.force_login(user)
    url = reverse("admin:crm_company_change", args=[org.pk])
    day = datetime(2026, 10, 22).date()

    def add_call(title: str, hour: int) -> Any:
        posted = _admin_change_post(client, url)
        index = int(posted["planned_touches-TOTAL_FORMS"])
        posted["planned_touches-TOTAL_FORMS"] = str(index + 1)
        posted[f"planned_touches-{index}-id"] = ""
        posted[f"planned_touches-{index}-company"] = str(org.pk)
        posted[f"planned_touches-{index}-starts_at_0"] = day.isoformat()
        posted[f"planned_touches-{index}-starts_at_1"] = f"{hour:02d}:00:00"
        posted[f"planned_touches-{index}-status"] = "planned"
        posted[f"planned_touches-{index}-assignee"] = ""
        posted[f"planned_touches-{index}-title"] = title
        response = client.post(url, posted)
        if response.status_code != 302:
            form_errors = [f"status={response.status_code}"]
            if response.context is not None:
                form_errors.append(str(response.context["adminform"].form.errors))
                for formset in response.context["inline_admin_formsets"]:
                    forms = formset.formset
                    form_errors.append(f"{forms.prefix} {forms.non_form_errors()} {forms.errors}")
            raise AssertionError(" | ".join(form_errors))
        return response

    add_call("Первый", 10)
    add_call("Второй", 10)
    saved = list(PlannedTouch.objects.filter(company=org).order_by("pk"))
    assert [row.title for row in saved] == ["Первый", "Второй"]
    canonical = touch_dedupe_key(org.pk, saved[0].kind, day)
    assert saved[0].dedupe_key == canonical
    assert saved[1].dedupe_key != canonical
    assert saved[1].dedupe_key.startswith(f"{canonical}:")
    assert timezone.localtime(saved[0].starts_at).date() == day
