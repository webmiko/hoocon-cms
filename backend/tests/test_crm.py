"""Tests for CRM: Client from Lead, outbound email, Admin registry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import site
from django.core import mail
from django.urls import reverse

from crm.models import Activity, ActivityType, Client, EmailMessage, EmailStatus
from crm.services import create_outbound_email, get_or_create_client_from_lead
from leads.models import Lead
from tests.mail_compose_helpers import assert_send_now_is_one_label


@pytest.mark.django_db
def test_crm_models_registered_in_admin() -> None:
    """Client, Activity, EmailMessage are in admin.site."""
    assert Client in site._registry
    assert Activity in site._registry
    assert EmailMessage in site._registry


@pytest.mark.django_db
def test_new_lead_auto_creates_and_links_client() -> None:
    """post_save on Lead creates Client and sets Lead.client."""
    lead = Lead.objects.create(
        name="Иван Петров",
        email="ivan.crm@example.com",
        phone="+79001234567",
        company="ООО Тест",
        message="Нужен КП",
    )
    lead.refresh_from_db()
    assert lead.client_id is not None
    client = lead.client
    assert client is not None
    assert client.email.lower() == "ivan.crm@example.com"
    # Неподтверждённый контакт: карточка нейтральная до verify-flip.
    assert client.name == "ivan.crm@example.com"
    assert client.company == ""
    assert client.phone == ""
    from crm.services import record_lead_inbound

    Lead.objects.filter(pk=lead.pk).update(contact_verified=True)
    lead.refresh_from_db()
    record_lead_inbound(lead)
    client.refresh_from_db()
    assert client.name == "Иван Петров"
    assert client.company == "ООО Тест"
    assert client.phone == "+79001234567"


@pytest.mark.django_db
def test_second_lead_same_email_reuses_client() -> None:
    """Two leads with same email share one Client card; verified merges fields."""
    Lead.objects.create(
        name="Anna",
        email="shared@example.com",
        message="First",
    )
    lead2 = Lead.objects.create(
        name="Anna 2",
        email="shared@example.com",
        message="Second",
        company="NewCo",
        contact_verified=True,
    )
    lead2.refresh_from_db()
    assert Client.objects.filter(email__iexact="shared@example.com").count() == 1
    assert lead2.client is not None
    assert lead2.client.company == "NewCo"
    assert lead2.client.leads.count() == 2


@pytest.mark.django_db
def test_matching_email_name_company_stays_one_client() -> None:
    """Same ID + name + company → one card; both leads listed on it."""
    Lead.objects.create(
        name="Иван",
        email="same.id@example.com",
        company="ООО Ромашка",
        message="Первая",
    )
    lead2 = Lead.objects.create(
        name="Иван",
        email="same.id@example.com",
        company="ООО Ромашка",
        message="Вторая",
    )
    lead2.refresh_from_db()
    assert Client.objects.filter(email="same.id@example.com").count() == 1
    client = lead2.client
    assert client is not None
    assert set(client.leads.values_list("message", flat=True)) == {"Первая", "Вторая"}


@pytest.mark.django_db
def test_client_change_form_lists_leads_inline(client, django_user_model) -> None:
    """Client card shows attached leads (not a second client)."""
    user = django_user_model.objects.create_user(
        username="crm-inline",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    Lead.objects.create(
        name="Иван",
        email="card@example.com",
        company="ООО",
        message="Заявка А",
    )
    Lead.objects.create(
        name="Иван",
        email="card@example.com",
        company="ООО",
        message="Заявка Б",
    )
    crm_client = Client.objects.get(email="card@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_change", args=[crm_client.pk])
    html = client.get(url).content.decode()
    assert "Заявка А" in html
    assert "Заявка Б" in html
    assert "лиды клиента" in html.lower()
    # Unfold action_list (e.g. История) — phone shell relocates into «Ещё» via JS.
    assert "data-hoocon-phone-action-list" in html
    assert "/history/" in html
    assert "История" in html


@pytest.mark.django_db
def test_client_change_form_shows_blank_activity_and_document_rows(client, django_user_model) -> None:
    """Empty client card: one blank tabular row per inline until the first save."""
    user = django_user_model.objects.create_user(
        username="crm-activity-extra",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_change", args=[crm_client.pk])
    html = client.get(url).content.decode()
    assert 'name="activities-0-subject"' in html
    assert 'name="documents-0-title"' in html
    assert "activities-__prefix__" in html
    assert "documents-__prefix__" in html


@pytest.mark.django_db
def test_get_or_create_client_from_lead_dedupes() -> None:
    """Service finds existing Client by email case-insensitively."""
    existing = Client.objects.create(
        name="Exist",
        email="dedup@example.com",
    )
    lead = Lead.objects.create(
        name="New Name",
        email="Dedup@Example.com",
        message="msg",
    )
    # Signal already linked; service should return same client.
    client = get_or_create_client_from_lead(lead)
    assert client.pk == existing.pk


@pytest.mark.django_db
def test_get_or_create_client_from_lead_locks_before_merge() -> None:
    """Existing Client is re-locked before merging lead contact data.

    Regresses concurrent leads with the same email overwriting the merge.
    """
    from unittest.mock import patch

    existing = Client.objects.create(name="Ivan", email="merge.lock@example.com")
    lead = Lead.objects.create(
        name="Ivan 2",
        email="merge.lock@example.com",
        message="msg",
        company="NewCo",
        contact_verified=True,  # M1: поля карточки дополняет только доказанный контакт
    )
    with patch("crm.services.Client.objects.select_for_update") as mock_sf:
        mock_sf.return_value.get.return_value = existing
        client = get_or_create_client_from_lead(lead)

    mock_sf.assert_called_once()
    assert mock_sf.return_value.get.call_args.kwargs["pk"] == existing.pk
    assert client.company == "NewCo"


@pytest.mark.django_db
def test_unverified_lead_company_lands_in_notes_not_the_field() -> None:
    """M1: подделанная заявка не пишет «Компанию» — только подсказку в заметки.

    Symptom: verified-only merge dropped the unverified lead's company
    entirely — a real sender's «ООО "СпецКомлект-С"» never reached the card.
    """
    lead = Lead.objects.create(
        name="Тарасов",
        email="tarasov.hint@yandex.ru",
        company='ООО "СпецКомлект-С"',
        message="Просим КП",
    )
    lead.refresh_from_db()
    client = lead.client
    assert client is not None
    assert client.company == ""
    assert f"заявке #{lead.pk}" in client.notes
    assert "СпецКомлект-С" in client.notes


@pytest.mark.django_db
def test_unverified_company_hint_written_once() -> None:
    """Повторный проход по той же заявке не дублирует строку-подсказку."""
    lead = Lead.objects.create(
        email="hint.once@mail.ru",
        company='ООО "Раз"',
        message="x",
    )
    get_or_create_client_from_lead(lead)
    client = get_or_create_client_from_lead(lead)
    assert client.notes.count("указана компания") == 1


@pytest.mark.django_db
def test_verified_lead_company_fills_field_without_hint() -> None:
    """Верифицированная заявка пишет «Компанию» — строки-подсказки нет."""
    lead = Lead.objects.create(
        email="verified.hint@corp.test",
        company='ООО "Верная"',
        contact_verified=True,
        message="x",
    )
    client = get_or_create_client_from_lead(lead)
    client.refresh_from_db()
    assert client.company == 'ООО "Верная"'
    assert "указана компания" not in client.notes


@pytest.mark.django_db
def test_backfill_company_refs_links_update_bypassed_rows() -> None:
    """Sweep: строка с company через update() получает карточку и членство.

    ``ensure_company_ref`` живёт в ``Client.save()`` — bulk-пути оставляют
    ``company`` заполненным при ``company_ref`` пустом (прод-долг 17.11).
    """
    from crm.models import CompanyMember
    from crm.tasks import backfill_company_refs

    client = Client.objects.create(email="debt.sweep@mail.ru", name="D")
    Client.objects.filter(pk=client.pk).update(company='ООО "Долг"')
    client.refresh_from_db()
    assert client.company_ref_id is None
    assert client.company_key == ""  # save() не запускался — ключ устарел

    report = backfill_company_refs()

    client.refresh_from_db()
    org = client.company_ref
    assert org is not None
    assert org.name == 'ООО "Долг"'
    assert client.company_key == "ооо долг"
    assert CompanyMember.objects.filter(company=org, client=client).exists()
    assert report == "debt=1 linked=1"

    assert backfill_company_refs() == "debt=0 linked=0"  # идемпотентна


@pytest.mark.django_db
def test_backfill_company_refs_clears_whitespace_only_label() -> None:
    """Пробельная строка не образует ключ — сбрасываем, чтобы не висела долгом."""
    from crm.tasks import backfill_company_refs

    client = Client.objects.create(email="blank.sweep@mail.ru", name="B")
    Client.objects.filter(pk=client.pk).update(company="   ")

    assert backfill_company_refs() == "debt=1 linked=0"

    client.refresh_from_db()
    assert client.company == ""
    assert client.company_ref_id is None
    assert backfill_company_refs() == "debt=0 linked=0"


@pytest.mark.django_db
def test_company_refs_sweep_periodic_task_registered() -> None:
    """Миграция регистрирует ежедневный sweep — регресс на beat-расписание."""
    from django_celery_beat.models import PeriodicTask

    task = PeriodicTask.objects.get(name="crm.backfill_company_refs")
    assert task.enabled is True
    assert task.task == "crm.backfill_company_refs"
    assert task.crontab is not None


def test_company_guess_skips_our_own_org() -> None:
    """Подпись «ООО "Хогон"» из пересланного письма — не компания клиента."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body="С уважением,\nАлександр\nООО «Хогон»\nsales@hoocon.ru",
    )
    assert guess == ""


def test_company_guess_prefers_signature_over_quoted_history() -> None:
    """Организация ищется до цитаты «… писал(а):» — чужая подпись внизу не считается."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body=(
            "Добрый день!\n\nС уважением,\nИван\n"
            'ООО "Отправитель"\n\n17.11.2026, sales@hoocon.ru писал(а):\n'
            "> С уважением,\n> ООО «Хогон»"
        ),
    )
    assert guess == "ООО «Отправитель»"


def test_company_guess_ignores_sip_cable_brand() -> None:
    """«СИП Иванов» — марка кабеля из нашего каталога, не «ИП Иванов»."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body="С уважением,\nСИП Иванов\nинженер",
    )
    assert guess == ""


def test_company_guess_signoff_must_start_a_line() -> None:
    """«с уважением» внутри фразы не открывает зону подписи.

    Среднее-2 ревью: маркер-подстрока открывал зону до конца письма и
    упоминание третьей стороны становилось карточкой юрлица.
    """
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body=("Прошу отнестись с уважением к срокам.\nМы работаем с ООО «Рога» по проекту.\nИван"),
    )
    assert guess == ""


def test_company_guess_single_line_letter_no_org() -> None:
    """Однострочное письмо: упоминание юрлица в просьбе — не подпись."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body='Пришлите цены на ООО "Рога"',
    )
    assert guess == ""


def test_company_guess_header_line_inside_letter_keeps_signature() -> None:
    """«Тема:»/«Дата:» в тексте отправителя — не шапка цитаты.

    Среднее ревью-2: одиночная строка-заголовок до «С уважением» обрывала
    письмо — подпись терялась, а юрлицо над заголовком («Партнёр»)
    ошибочно становилось компанией отправителя.
    """
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body="ООО «Партнёр»\n\nТема: совместная поставка\n\nС уважением,\nООО «Наша»",
    )
    assert guess == "ООО «Наша»"

    guess = company_guess_from_letter(
        subject="",
        body="Добрый день!\n\nТема: запрос КП\n\nС уважением,\nПетров\nООО «Рога»",
    )
    assert guess == "ООО «Рога»"


def test_company_guess_quote_headers_after_signature_still_cut() -> None:
    """Блок «От:/Кому:/Тема:» ПОСЛЕ своей подписи — по-прежнему граница."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body=(
            "Просим КП.\n\nС уважением,\nООО «Рога»\n\n"
            "От: Менеджер\nОтправлено: 17.11.2026\nКому: sales@hoocon.ru\n"
            "Тема: Re: цены\n\nС уважением,\nООО «Хогон»"
        ),
    )
    assert guess == "ООО «Рога»"


def test_company_guess_standalone_org_line_without_signoff() -> None:
    """Без «С уважением» строка целиком «ООО «Рога»» — всё же подпись."""
    from crm.company import company_guess_from_letter

    guess = company_guess_from_letter(
        subject="",
        body="Просим цены на 8100.\nИван Петров\nООО «Рога»",
    )
    assert guess == "ООО «Рога»"


@pytest.mark.django_db
def test_note_hint_on_debt_row_persists_company_key() -> None:
    """Заметка-подсказка на строке-долге доносит ключ в базу.

    ``update(company=...)`` обошёл save(): ключ в базе пуст. Дозапись
    заметки через ``update_fields`` обязана нести пересчитанный ключ —
    иначе карточка свяжется, а строка останется вечным долгом без
    маршрутизации по ключу (среднее-3 ревью).
    """
    client = Client.objects.create(email="debt.note@mail.ru", name="D")
    Client.objects.filter(pk=client.pk).update(company='ООО "Долг"')

    lead = Lead.objects.create(
        email="debt.note@mail.ru",
        company='ООО "Совсем другая"',
        message="x",
    )
    lead.refresh_from_db()
    client = lead.client
    assert client is not None
    client.refresh_from_db()

    assert "указана компания" in client.notes
    assert client.company == 'ООО "Долг"'  # поле не тронули
    assert client.company_key == "ооо долг"  # а ключ в базе есть
    assert client.company_ref is not None


@pytest.mark.django_db(transaction=True)
def test_ensure_company_ref_recovers_from_create_race() -> None:
    """Гонка INSERT одного company_key: savepoint спасает fallback.

    Без вложенного atomic() пойманный IntegrityError делает внешнюю
    транзакцию письма аварийной на Postgres — следующий filter() падает
    InternalError и письмо теряется без дедуп-метки (UID уходит вперёд).
    """
    from unittest.mock import patch

    from django.db import transaction

    from crm.company import ensure_company_ref
    from crm.models import Company

    winner = Company.objects.create(name='ООО "Гонка"')
    client = Client.objects.create(email="race.ensure@mail.ru", name="R")
    client.company = 'ООО "Гонка"'
    client.company_key = "ооо гонка"

    real_filter = Company.objects.filter
    real_create = Company.objects.create
    calls = {"filter": 0}

    def _first_filter_misses(*args, **kwargs):
        calls["filter"] += 1
        queryset = real_filter(*args, **kwargs)
        if calls["filter"] == 1:
            return queryset.exclude(pk=winner.pk)
        return queryset

    with (
        patch.object(Company.objects, "filter", side_effect=_first_filter_misses),
        patch.object(Company.objects, "create", side_effect=lambda **kw: real_create(**kw)),
        transaction.atomic(),
    ):
        org = ensure_company_ref(client)

    assert org is not None and org.pk == winner.pk
    client.refresh_from_db()
    assert client.company_ref_id == winner.pk


@pytest.mark.django_db(transaction=True)
def test_create_outbound_email_queues_and_logs_activity(
    settings,
    django_user_model,
) -> None:
    """create_outbound_email creates EmailMessage + Activity and enqueues."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "sales@hoocon.test"

    user = django_user_model.objects.create_user(
        username="mgr",
        password="test-pass-not-secret",
        is_staff=True,
    )
    client = Client.objects.create(name="Buyer", email="buyer@example.com")

    with patch("crm.tasks.send_crm_email.delay") as delay_mock:
        msg = create_outbound_email(
            client=client,
            subject="КП по приводам",
            body="Добрый день, во вложении КП.",
            author=user,
            send_now=True,
        )

    assert msg.status == EmailStatus.QUEUED
    assert msg.to_email == "buyer@example.com"
    assert msg.from_email == "sales@hoocon.test"
    assert Activity.objects.filter(
        client=client,
        activity_type=ActivityType.EMAIL,
        subject="КП по приводам",
    ).exists()
    delay_mock.assert_called_once_with(msg.pk)


@pytest.mark.django_db
def test_send_crm_email_task_marks_sent(settings) -> None:
    """Celery task sends via Django mail and marks EmailMessage SENT."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "sales@hoocon.test"

    client = Client.objects.create(name="Buyer", email="buyer@example.com")
    msg = EmailMessage.objects.create(
        client=client,
        to_email="buyer@example.com",
        from_email="sales@hoocon.test",
        subject="Hello",
        body="Body text",
        status=EmailStatus.QUEUED,
    )

    from crm.tasks import send_crm_email

    send_crm_email(msg.pk)
    msg.refresh_from_db()
    assert msg.status == EmailStatus.SENT
    assert msg.sent_at is not None
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Hello"
    assert mail.outbox[0].to == ["buyer@example.com"]


@pytest.mark.django_db
def test_send_crm_email_task_marks_failed_on_smtp_error(settings) -> None:
    """On SMTP failure, status becomes FAILED and task retries."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client = Client.objects.create(name="Buyer", email="buyer@example.com")
    msg = EmailMessage.objects.create(
        client=client,
        to_email="buyer@example.com",
        from_email="sales@hoocon.test",
        subject="Fail",
        body="x",
        status=EmailStatus.QUEUED,
    )

    from crm.tasks import send_crm_email

    with patch("crm.tasks.DjangoEmailMessage.send", side_effect=OSError("smtp down")):
        with patch.object(send_crm_email, "retry", side_effect=RuntimeError("retry")):
            with pytest.raises(RuntimeError, match="retry"):
                send_crm_email.run(msg.pk)

    msg.refresh_from_db()
    assert msg.status == EmailStatus.FAILED
    assert "OSError" in msg.error_message


@pytest.mark.django_db
def test_staff_can_open_client_changelist(client, django_user_model) -> None:
    """Staff gets 200 on CRM Client changelist; ID column is email."""
    user = django_user_model.objects.create_user(
        username="crm-editor",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    Client.objects.create(name="Иван", email="ivan.group@example.com")
    Client.objects.create(name="Пётр", email="peter.group@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_changelist")
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "ivan.group@example.com" in html
    assert "peter.group@example.com" in html
    # Sorted by email → ivan before peter.
    assert html.index("ivan.group@example.com") < html.index("peter.group@example.com")


@pytest.mark.django_db
def test_activity_changelist_groups_by_client_email(client, django_user_model) -> None:
    """Activity list shows email as ID and orders same emails together."""
    user = django_user_model.objects.create_user(
        username="crm-act",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    a = Client.objects.create(name="A", email="a@example.com")
    b = Client.objects.create(name="B", email="b@example.com")
    Activity.objects.create(client=b, subject="B late", author=user)
    Activity.objects.create(client=a, subject="A first", author=user)
    Activity.objects.create(client=a, subject="A second", author=user)
    client.force_login(user)
    html = client.get(reverse("admin:crm_activity_changelist")).content.decode()
    assert html.count("a@example.com") >= 2
    assert html.index("a@example.com") < html.index("b@example.com")


@pytest.mark.django_db(transaction=True)
def test_compose_email_view_creates_queued_message(
    client,
    django_user_model,
    settings,
) -> None:
    """POST compose-email queues outbound mail for the Client."""
    # Eager: Activity on_commit also enqueues Telegram; avoid live Redis.
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DEFAULT_FROM_EMAIL = "sales@hoocon.test"
    user = django_user_model.objects.create_user(
        username="crm-mailer",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])

    with patch("crm.tasks.send_crm_email.delay") as delay_mock:
        response = client.post(
            url,
            {
                "to_email": "buyer@example.com",
                "subject": "КП",
                "body": "Текст письма менеджера",
                "send_now": "on",
            },
        )

    assert response.status_code == 302
    msg = EmailMessage.objects.get(client=crm_client)
    assert msg.subject == "КП"
    assert msg.status == EmailStatus.QUEUED
    delay_mock.assert_called_once_with(msg.pk)


@pytest.mark.django_db
def test_compose_email_rejects_body_over_character_limit(client, django_user_model) -> None:
    """Текст длиннее 20 000 символов не уходит: форма показывает, что лимит исчерпан."""
    user = django_user_model.objects.create_user(
        username="crm-mailer-limit",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="limit@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])

    response = client.post(
        url,
        {
            "to_email": "limit@example.com",
            "subject": "КП",
            "body": "а" * 20001,
            "send_now": "on",
        },
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Лимит 20 000 символов исчерпан" in html
    assert not EmailMessage.objects.filter(client=crm_client).exists()
    # source-lint: страница грузит этот скрипт; он же не даёт отправить текст сверх maxlength.
    script = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-mail-compose.js").read_text(
        encoding="utf-8"
    )
    assert "refreshLimit" in script
    assert 'setAttribute("role", over ? "alert"' in script
    assert "event.preventDefault()" in script


@pytest.mark.django_db
def test_compose_email_renders_mail_client_surface(client, django_user_model) -> None:
    """Client compose-email uses the mail-client chrome (CSS+JS loaded surface).

    Bare admin form markup rendered the composer as unstyled fields — the page
    must carry hoocon-mail-compose chrome, editor, toolbar and its assets.
    """
    user = django_user_model.objects.create_user(
        username="crm-mailer-ui",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])

    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-mail-compose.css" in html
    assert "hoocon-mail-compose.js" in html
    assert "hoocon-mail-compose__editor" in html
    assert 'id="hoocon-mail-compose-form"' in html
    assert "hoocon-mail-compose__toolbar" in html


@pytest.mark.django_db
def test_import_spec_page_renders_unfold_surface(client, django_user_model) -> None:
    """Spec import page uses Unfold field/button helpers, not bare stock markup."""
    user = django_user_model.objects.create_user(
        username="crm-import-ui",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_import_spec", args=[crm_client.pk])

    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="id_file"' in html
    assert "Импортировать" in html
    assert "submit-row" not in html
    assert 'class="form-row"' not in html
    # Кнопка «Скачать шаблон» — снижает ошибки в формате файла.
    assert f"/admin/crm/client/{crm_client.pk}/import-spec/template/" in html
    assert "Скачать шаблон" in html


@pytest.mark.django_db
def test_import_spec_template_download(client, django_user_model) -> None:
    """Шаблон спеки отдаётся валидным .xlsx с колонками, которые понимает парсер."""
    import io

    import openpyxl

    user = django_user_model.objects.create_user(
        username="crm-import-tpl",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_import_spec_template", args=[crm_client.pk])

    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert "hoocon-spec-template.xlsx" in response["Content-Disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    header = [c.value for c in wb.worksheets[0][1]]
    wb.close()
    assert header == ["Артикул", "Наименование", "Количество"]

    # Шаблон проходит через боевой парсер без правок.
    from cabinet.spec_import import parse_spec_xlsx

    rows = parse_spec_xlsx(io.BytesIO(response.content))
    assert len(rows) >= 1


@pytest.mark.django_db
def test_anon_cannot_download_spec_template(client) -> None:
    """Шаблон спеки недоступен анониму."""
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    url = reverse("admin:crm_client_import_spec_template", args=[crm_client.pk])
    response = client.get(url)
    assert response.status_code == 302
    assert "/admin/login" in response.url


@pytest.mark.django_db
def test_anon_cannot_compose_email(client) -> None:
    """Anonymous users are redirected from compose-email."""
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])
    response = client.get(url)
    assert response.status_code == 302
    assert "/admin/login" in response.url


@pytest.mark.django_db
def test_compose_email_send_now_renders_as_toggle(client, django_user_model) -> None:
    """Client compose shows Черновик/Отправить сразу once, inside the switch label only."""
    user = django_user_model.objects.create_superuser(
        username="crm-toggle",
        email="mgr@hoocon.ru",
        password="x",
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])
    html = client.get(url).content.decode()
    assert_send_now_is_one_label(html)


@pytest.mark.django_db
def test_client_email_unique_normalized() -> None:
    """Client.email is unique after lowercase normalization on save."""
    from django.db import IntegrityError

    Client.objects.create(name="A", email="Unique@Example.com")
    with pytest.raises(IntegrityError):
        Client.objects.create(name="B", email="unique@example.com")


@pytest.mark.django_db
def test_client_company_key_normalized_on_save() -> None:
    """company_key mirrors normalize_company_label («ООО "Ромашка"» → «ооо ромашка»)."""
    client_obj = Client.objects.create(
        name="Иван",
        email="company-key@example.com",
        company="  ООО «Ромашка» ",
    )
    assert client_obj.company_key == "ооо ромашка"
    client_obj.company = 'ООО   "Лютик"'
    client_obj.save()
    assert client_obj.company_key == "ооо лютик"


@pytest.mark.django_db
def test_client_change_form_lists_support_conversations(client, django_user_model) -> None:
    """Linked supportchat dialogs render on the client card (read-only inline)."""
    from supportchat.models import Conversation

    user = django_user_model.objects.create_user(
        username="crm-conv-inline",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Пётр", email="conv@example.com")
    Conversation.objects.create(
        channel="web",
        external_user_id="sess-conv-inline-1",
        display_name="Пётр с сайта",
        client=crm_client,
    )
    client.force_login(user)
    url = reverse("admin:crm_client_change", args=[crm_client.pk])
    html = client.get(url).content.decode()
    assert "диалоги поддержки" in html.lower()
    assert "Пётр с сайта" in html


@pytest.mark.django_db
def test_email_list_filters_by_the_manager_who_wrote_it(client, django_user_model) -> None:
    """Журнал «Письма»: фильтр «менеджер» оставляет письма автора и не показывает чужие."""
    from django.contrib.auth.models import Group

    from accounts.roles import GROUP_MANAGER
    from accounts.services import ensure_staff_groups

    ensure_staff_groups()
    admin = django_user_model.objects.create_superuser("mail-filter", "mail-filter@example.com", "x")
    group = Group.objects.get(name=GROUP_MANAGER)

    def manager(username: str, first_name: str):
        person = django_user_model.objects.create_user(
            username=username,
            password="x",
            first_name=first_name,
            is_staff=True,
            is_active=True,
        )
        person.groups.add(group)
        return person

    alena = manager("mail-alena", "Алёна")
    boris = manager("mail-boris", "Борис")
    buyer = Client.objects.create(name="Покупатель", email="buyer-filter@example.com")
    EmailMessage.objects.create(
        client=buyer,
        to_email=buyer.email,
        subject="Письмо Алёны",
        body="Текст Алёны",
        created_by=alena,
    )
    EmailMessage.objects.create(
        client=buyer,
        to_email=buyer.email,
        subject="Письмо Бориса",
        body="Текст Бориса",
        created_by=boris,
    )
    EmailMessage.objects.create(
        client=buyer,
        to_email=buyer.email,
        subject="Входящее без автора",
        body="Входящий текст",
        direction="inbound",
    )
    client.force_login(admin)
    listing = reverse("admin:crm_emailmessage_changelist")
    html = client.get(listing).content.decode()
    assert "Исходящее" in html
    panel = html.split('id="changelist-filter"', 1)[1]
    assert f'?manager={alena.pk}"' in panel
    assert f'?manager={boris.pk}"' in panel
    assert f'<option value="{alena.pk}">' not in html
    assert panel.index("Алёна") < panel.index("Исходящее")
    filtered = client.get(listing, {"manager": str(alena.pk)}).content.decode()
    assert "Письмо Алёны" in filtered
    assert "Письмо Бориса" not in filtered
    assert "Входящее без автора" not in filtered


@pytest.mark.django_db(transaction=True)
def test_email_admin_queue_send_skips_already_queued(
    client,
    django_user_model,
) -> None:
    """queue_send action enqueues draft only once; skips QUEUED."""
    user = django_user_model.objects.create_user(
        username="crm-queue",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    draft = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer@example.com",
        from_email="sales@hoocon.test",
        subject="Draft",
        body="Body",
        status=EmailStatus.DRAFT,
    )
    queued = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer@example.com",
        from_email="sales@hoocon.test",
        subject="Already",
        body="Body",
        status=EmailStatus.QUEUED,
    )
    from django.core.cache import cache
    from django.utils import timezone

    from crm.tasks import _EMAIL_SEND_STAMP

    cache.set(_EMAIL_SEND_STAMP.format(pk=queued.pk), timezone.now().timestamp(), timeout=3600)
    client.force_login(user)
    with patch("crm.tasks.send_crm_email.delay") as delay_mock:
        response = client.post(
            reverse("admin:crm_emailmessage_changelist"),
            {
                "action": "queue_send",
                "_selected_action": [str(draft.pk), str(queued.pk)],
            },
        )
    assert response.status_code in {200, 302}
    delay_mock.assert_called_once_with(draft.pk)
    draft.refresh_from_db()
    assert draft.status == EmailStatus.QUEUED


@pytest.mark.django_db(transaction=True)
def test_email_admin_save_does_not_reenqueue_queued(
    client,
    django_user_model,
) -> None:
    """Editing an already QUEUED message does not call delay again."""
    user = django_user_model.objects.create_user(
        username="crm-edit-q",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer2@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer2@example.com",
        from_email="sales@hoocon.test",
        subject="Queued",
        body="Body text here",
        status=EmailStatus.QUEUED,
        created_by=user,
    )
    client.force_login(user)
    url = reverse("admin:crm_emailmessage_change", args=[msg.pk])
    with patch("crm.tasks.send_crm_email.delay") as delay_mock:
        response = client.post(
            url,
            {
                "client": crm_client.pk,
                "direction": "outbound",
                "status": EmailStatus.QUEUED,
                "to_email": "buyer2@example.com",
                "from_email": "sales@hoocon.test",
                "subject": "Queued edited",
                "body": "Body text here",
            },
        )
    assert response.status_code in {200, 302}
    delay_mock.assert_not_called()
