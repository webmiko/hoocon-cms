"""Tests for CRM: Client from Lead, outbound email, Admin registry."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import site
from django.core import mail
from django.urls import reverse

from crm.models import Activity, ActivityType, Client, EmailMessage, EmailStatus
from crm.services import create_outbound_email, get_or_create_client_from_lead
from leads.models import Lead


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
    assert client.name == "Иван Петров"
    assert client.company == "ООО Тест"
    assert client.phone == "+79001234567"


@pytest.mark.django_db
def test_second_lead_same_email_reuses_client() -> None:
    """Two leads with same email share one Client card."""
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
    assert "заявки клиента" in html.lower() or "Заявки" in html
    # Unfold action_list (e.g. История) — phone shell relocates into «Ещё» via JS.
    assert "data-hoocon-phone-action-list" in html
    assert "/history/" in html
    assert "История" in html


@pytest.mark.django_db
def test_client_change_form_no_empty_activity_row(client, django_user_model) -> None:
    """Activity inline: no always-visible empty row — «Добавить» clones __prefix__ form."""
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
    # extra=0 → нет реальной строки №0 без существующих активностей/документов.
    assert 'name="activities-0-subject"' not in html
    assert 'id="id_activities-0-subject"' not in html
    assert 'name="documents-0-title"' not in html
    # Кнопка «Добавить» остаётся рабочей — JS клонирует пустой шаблон.
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
    )
    with patch("crm.services.Client.objects.select_for_update") as mock_sf:
        mock_sf.return_value.get.return_value = existing
        client = get_or_create_client_from_lead(lead)

    mock_sf.assert_called_once()
    assert mock_sf.return_value.get.call_args.kwargs["pk"] == existing.pk
    assert client.company == "NewCo"


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
    """CRM compose uses the same hoocon-toggle switch skin for send_now."""
    user = django_user_model.objects.create_superuser(
        username="crm-toggle",
        email="mgr@hoocon.ru",
        password="x",
    )
    crm_client = Client.objects.create(name="Buyer", email="buyer@example.com")
    client.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])
    html = client.get(url).content.decode()
    assert 'type="checkbox"' in html
    assert 'class="hoocon-toggle"' in html


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
