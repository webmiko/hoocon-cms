"""Company outreach: marks from notes, niche workbook, planned-call reminders."""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from openpyxl import Workbook

from accounts.models import StaffMaxProfile
from crm.client_import import import_clients_xlsx
from crm.models import Client, Company, PlannedTouch, WorkLabel
from crm.outreach import notify_due_touches
from crm.work_labels import (
    extract_contact_name,
    labels_for_note,
    loose_company_key,
    planned_call_date,
)

HEADERS = ["Компания", "ИНН", "Юридический адрес", "Контакт", "Эл. почта", "Телефон", "Заметки"]
BASE_HEADERS = [
    "№",
    "Ниша HOOCON",
    "Компания",
    "Город",
    "Сайт",
    "Телефон",
    "Email",
    "Профиль (из базы)",
    "Регион базы",
    "Релевантность",
]


def _xlsx(rows: list[list[object]]) -> BytesIO:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    book.save(buf)
    buf.seek(0)
    return buf


def test_note_marks_follow_the_outreach_workbook() -> None:
    """Phrases from the 21.10 notes become the shared filter marks."""
    assert labels_for_note(
        "Не прозвонен (дубль базы) — сверить с действующими клиентами",
    ) == frozenset({"not_called", "duplicate", "verify_base"})
    assert labels_for_note("Исключён из прозвона | НЕ ЗВОНИТЬ | Дубль базы") == frozenset(
        {"do_not_call", "duplicate"},
    )
    assert "duplicate" not in labels_for_note("не дублировать второе КП")
    warning = "⚠ Checko 21.10: исполнительное производство — отгрузка только по предоплате."
    assert labels_for_note(warning) == frozenset({"checko_warning", "prepaid_only"})
    assert labels_for_note("Уже работаем | НЕ ЗВОНИТЬ") == frozenset({"existing_client", "do_not_call"})
    assert "do_not_call" not in labels_for_note("КП ВЫСЛАНО 21.10 | Действующий клиент")
    assert labels_for_note("КП ВЫСЛАНО 21.10 | Действующий клиент") == frozenset(
        {"quote_sent", "existing_client"},
    )
    assert planned_call_date("Звонок по плану: 22.10 (чт)", today=date(2026, 10, 21)) == date(2026, 10, 22)
    assert planned_call_date("Звонок по плану: 22.10", today=date(2026, 12, 20)) == date(2027, 10, 22)


def test_short_legal_name_matches_the_full_one() -> None:
    """The niche sheet drops «ООО» and quotes. That is still the same company."""
    assert loose_company_key("ООО «АЗ АТОМ»") == loose_company_key("АЗ АТОМ")
    assert loose_company_key("ООО НПК «Хилтех»") == loose_company_key("НПК Хилтех")
    assert loose_company_key("ООО «ППМ» (Промпроектмаш)") == loose_company_key("ППМ (ПромПроектМаш)")
    assert (
        extract_contact_name(
            "Пожарное оборудование. Контакт: Халиуллин Ильдар Ильясович",
        )
        == "Халиуллин Ильдар Ильясович"
    )
    assert extract_contact_name("Автоматика, директор Абдреев Рафаиль Ирекович") == ("Абдреев Рафаиль Ирекович")


@pytest.mark.django_db
def test_template_row_without_email_creates_company_call_and_marks() -> None:
    """A planned call in the notes lands on the company even when there is no mailbox."""
    report = import_clients_xlsx(
        _xlsx(
            [
                HEADERS,
                [
                    "ООО «Ромашка»",
                    "",
                    "Казань",
                    "уточнить",
                    "",
                    "8 (800) 222-99-40",
                    "Не прозвонен | Звонок по плану: 22.10 (чт) | Скрипт: спросить ЛПР",
                ],
            ],
        ),
    )
    assert report.created == 0
    assert report.companies_created == 1
    assert report.touches_created == 1
    assert Client.objects.count() == 0
    org = Company.objects.get()
    assert org.phone == "8 (800) 222-99-40"
    assert set(org.work_labels.values_list("code", flat=True)) == {"not_called"}
    touch = PlannedTouch.objects.get()
    when = timezone.localtime(touch.starts_at)
    assert (when.day, when.month, when.hour) == (22, 10, 10)
    again = import_clients_xlsx(
        _xlsx(
            [
                HEADERS,
                ["ООО «Ромашка»", "", "", "уточнить", "", "", "Не прозвонен | Звонок по плану: 22.10 (чт)"],
            ],
        ),
    )
    assert again.companies_created == 0
    assert again.touches_created == 0
    assert Company.objects.count() == 1
    assert PlannedTouch.objects.count() == 1


@pytest.mark.django_db
def test_niche_sheet_fills_the_same_company_card() -> None:
    """«АЗ АТОМ» from the base sheet updates ООО «АЗ АТОМ» instead of a second card."""
    Company.objects.create(name="ООО «АЗ АТОМ»", inn="1660155595", legal_address="Казань, Химград")
    report = import_clients_xlsx(
        _xlsx(
            [
                BASE_HEADERS,
                [
                    "1",
                    "3 — Трубопроводная арматура",
                    "АЗ АТОМ",
                    "Казань",
                    "az-atom.ru",
                    "+7 (843) 265-89-59, +7 (800) 250-87-08",
                    "rd@az-atom.ru; snab@az-atom.ru",
                    "Клапаны. Контакт: Зубков В.С.",
                    "ПФО",
                    "Высокая — производитель клапанов",
                ],
                [
                    "2",
                    "11 — Промышленные предприятия",
                    "ТЕХНО-ДЕТАЛЬ",
                    "Елабуга",
                    "tehno-detal.ru",
                    "+7 929 722-99-98",
                    "",
                    "Производитель оборудования",
                    "ПФО",
                    "Средняя — нефтегазовое оборудование",
                ],
            ],
        ),
    )
    assert report.bad_rows == 0
    assert report.created == 2
    assert report.companies_created == 1
    assert Company.objects.count() == 2
    org = Company.objects.get(inn="1660155595")
    assert org.name == "ООО «АЗ АТОМ»"
    assert org.legal_address == "Казань, Химград"
    assert org.website == "az-atom.ru"
    assert org.city == "Казань"
    assert org.niche == "Трубопроводная арматура"
    assert org.relevance == "high"
    assert org.region == "ПФО"
    assert org.contact_name == "Зубков В.С."
    assert set(org.work_labels.values_list("code", flat=True)) >= {
        "niche-armature",
        "relevance-high",
        "region-pfo",
    }
    assert Client.objects.filter(email="rd@az-atom.ru").get().phone == "+7 (843) 265-89-59"
    assert Client.objects.filter(email="snab@az-atom.ru").exists()
    bare = Company.objects.get(name="ТЕХНО-ДЕТАЛЬ")
    assert bare.relevance == "medium"
    assert Client.objects.filter(company_ref=bare).count() == 0
    assert WorkLabel.objects.filter(code="niche-industry").exists()


@pytest.mark.django_db
def test_planned_call_reminds_once_by_email_and_max() -> None:
    """The assignee gets one email and one MAX message. A second beat does not repeat them."""
    user = get_user_model().objects.create_user(
        username="mgr-plan",
        email="mgr-plan@hoocon.ru",
        password="x",
        is_staff=True,
        is_active=True,
    )
    StaffMaxProfile.objects.create(user=user, max_user_id="4242", max_alerts_enabled=True)
    org = Company.objects.create(name="ООО «Ромашка»", assignee=user)
    starts = timezone.now() + timedelta(minutes=30)
    PlannedTouch.objects.create(
        company=org,
        assignee=user,
        starts_at=starts,
        title="Звонок: Ромашка",
        note="Спросить ЛПР",
        remind_before_minutes=60,
        dedupe_key="test-touch-1",
    )
    with (
        patch("django.core.mail.send_mail") as mail,
        patch("accounts.max_alerts.send_max_to_users", return_value=1) as max_send,
    ):
        assert notify_due_touches(now=timezone.now()) == 1
        assert mail.call_count == 1
        assert mail.call_args.kwargs["recipient_list"] == ["mgr-plan@hoocon.ru"]
        assert max_send.call_count == 1
        assert notify_due_touches(now=timezone.now()) == 0
        assert mail.call_count == 1


@pytest.mark.django_db
def test_unassigned_planned_call_does_not_notify() -> None:
    """No assignee means the event stays on the calendar and nobody is spammed."""
    org = Company.objects.create(name="ООО «Ромашка»")
    PlannedTouch.objects.create(
        company=org,
        starts_at=timezone.now() + timedelta(minutes=20),
        title="Звонок: Ромашка",
        dedupe_key="test-touch-2",
    )
    with patch("django.core.mail.send_mail") as mail:
        assert notify_due_touches(now=timezone.now()) == 0
    assert mail.call_count == 0
    touch = PlannedTouch.objects.get()
    assert touch.email_notified_at is None


@pytest.mark.django_db
def test_seed_wiki_explains_work_labels() -> None:
    """The manager guide names the queue filter and the planned-call reminder."""
    from io import StringIO

    from django.core.management import call_command

    from content.models import WikiDocument

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    assert "Можно звонить" in guide.body
    assert "Плановые звонки" in guide.body
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert changelog.index("changelog-work-labels") < changelog.index("changelog-sku-order-scope")
