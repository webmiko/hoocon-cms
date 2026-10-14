"""CRM email templates: model, placeholders, compose pickers, group perms."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Client, EmailTemplate
from crm.services import email_template_context_for_client, email_template_context_for_lead, render_email_template
from leads.models import Lead, LeadItem


def _superuser(django_user_model, username: str):
    """Staff superuser for Admin HTTP tests."""
    return django_user_model.objects.create_user(
        username=username,
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )


@pytest.mark.django_db
def test_email_template_registered_in_admin() -> None:
    """EmailTemplate is managed in Admin (compose pickers read it)."""
    assert EmailTemplate in site._registry


def test_render_email_template_substitutes_known_placeholders() -> None:
    """{имя}/{компания}/{почта}/{телефон} подставляются; прочие скобки — как есть."""
    tpl = EmailTemplate(
        name="T",
        subject="КП для {компания}",
        body="Здравствуйте, {имя}! {unknown} {",
    )
    subject, body = render_email_template(
        tpl,
        context={"имя": "Иван", "компания": "ООО Тест", "почта": "", "телефон": ""},
    )
    assert subject == "КП для ООО Тест"
    assert body == "Здравствуйте, Иван! {unknown} {"


def test_empty_placeholder_is_omitted_from_body() -> None:
    """Пустой {заказ} и пустой {телефон} не остаются в теле ни тегом, ни пустой строкой-дырой."""
    tpl = EmailTemplate(
        name="КП",
        subject="Для {компания}",
        body=(
            "Здравствуйте, {имя}!\n"
            "\n"
            "По вашему заказу:\n"
            "\n"
            "{заказ}\n"
            "\n"
            "почта — {почта}\n"
            "телефон — {телефон}\n"
            "\n"
            "Ждём ответ."
        ),
    )
    _subject, body = render_email_template(
        tpl,
        context={
            "имя": "Иван",
            "компания": "ООО Тест",
            "почта": "ivan@example.com",
            "телефон": "",
            "заказ": "",
        },
    )
    assert "{заказ}" not in body
    assert "{телефон}" not in body
    assert "телефон" not in body
    assert "ivan@example.com" in body
    assert "\n\n\n" not in body
    html_tpl = EmailTemplate(name="H", subject="", body="<p>Текст</p><p>{заказ}</p><p>Дальше</p>")
    _, html_body = render_email_template(html_tpl, context={"заказ": "   "})
    assert "{заказ}" not in html_body
    assert "<p></p>" not in html_body
    assert "Текст" in html_body
    assert "Дальше" in html_body


def test_render_email_template_escapes_public_values_in_html_body() -> None:
    """Имя из публичной формы заявки вставлялось в HTML-шаблон как разметка (XSS в редакторе письма)."""
    tpl = EmailTemplate(name="T", subject="{имя}", body="<p>Здравствуйте, {имя}!</p>")
    payload = '<img src=x onerror="alert(1)">'
    subject, body = render_email_template(tpl, context={"имя": payload})
    assert body == "<p>Здравствуйте, &lt;img src=x onerror=&quot;alert(1)&quot;&gt;!</p>"
    assert subject == payload

    plain = EmailTemplate(name="P", subject="", body="Здравствуйте, {имя}!")
    _, plain_body = render_email_template(plain, context={"имя": "Рога & Копыта"})
    assert plain_body == "Здравствуйте, Рога & Копыта!"


@pytest.mark.django_db
def test_email_template_context_for_client() -> None:
    """Context maps the Client card fields one to one."""
    client_obj = Client.objects.create(
        name="Иван",
        email="ctx@example.com",
        company="ООО Контур",
        phone="+7 900 111-22-33",
    )
    assert email_template_context_for_client(client_obj) == {
        "имя": "Иван",
        "компания": "ООО Контур",
        "почта": "ctx@example.com",
        "телефон": "+7 900 111-22-33",
        "заказ": "",
    }


@pytest.mark.django_db
def test_order_placeholder_uses_this_lead_items() -> None:
    """{заказ} в ответе на заявку — сообщение и позиции этой заявки."""
    lead = Lead.objects.create(
        name="Иван",
        email="order-tag@example.com",
        company="ООО Контур",
        message="Нужны приводы на заслонки",
    )
    LeadItem.objects.create(lead=lead, sku_code="DA05MU24", quantity=2)
    context = email_template_context_for_lead(lead)
    assert "Нужны приводы на заслонки" in context["заказ"]
    assert "DA05MU24 × 2" in context["заказ"]
    _subject, body = render_email_template(
        EmailTemplate(name="КП", subject="Заказ {компания}", body="Состав:\n{заказ}"),
        context=context,
    )
    assert "DA05MU24 × 2" in body
    assert "{заказ}" not in body


@pytest.mark.django_db
def test_order_placeholder_on_client_uses_latest_lead() -> None:
    """{заказ} в письме с карточки — последняя заявка клиента, не более ранняя."""
    client_obj = Client.objects.create(
        name="Иван",
        email="latest-order@example.com",
        company="ООО Контур",
    )
    older = Lead.objects.create(
        name="Иван",
        email=client_obj.email,
        company="ООО Контур",
        message="Старый заказ",
        client=client_obj,
    )
    LeadItem.objects.create(lead=older, sku_code="OLD1", quantity=1)
    newer = Lead.objects.create(
        name="Иван",
        email=client_obj.email,
        company="ООО Контур",
        message="Новый заказ",
        client=client_obj,
    )
    LeadItem.objects.create(lead=newer, sku_code="NEW9", quantity=4)
    order = email_template_context_for_client(client_obj)["заказ"]
    assert "NEW9 × 4" in order
    assert "OLD1" not in order


@pytest.mark.django_db
def test_order_placeholder_hides_colleague_lead(django_user_model) -> None:
    """{заказ} с карточки клиента не берёт более новую заявку чужого менеджера."""
    mgr_a = django_user_model.objects.create_user(username="ord-a", password="x", is_staff=True)
    mgr_b = django_user_model.objects.create_user(username="ord-b", password="x", is_staff=True)
    client_obj = Client.objects.create(name="Иван", email="scope-order@example.com", company="ООО Контур")
    own = Lead.objects.create(
        name="Иван",
        email=client_obj.email,
        company="ООО Контур",
        message="Свой заказ",
        client=client_obj,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr_a,
    )
    LeadItem.objects.create(lead=own, sku_code="OWN1", quantity=1)
    foreign = Lead.objects.create(
        name="Иван",
        email=client_obj.email,
        company="ООО Контур",
        message="Чужая скидка 40 процентов",
        client=client_obj,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr_b,
    )
    LeadItem.objects.create(lead=foreign, sku_code="HID9", quantity=1)
    order = email_template_context_for_client(client_obj, mgr_a)["заказ"]
    assert "OWN1" in order
    assert "HID9" not in order
    assert "скидка" not in order.casefold()


@pytest.mark.django_db
def test_client_compose_prefills_from_template(django_user_model) -> None:
    """?template=<pk> prefills subject/body with the client card data."""
    user = _superuser(django_user_model, "tpl-client")
    crm_client = Client.objects.create(
        name="Иван",
        email="tpl@example.com",
        company="ООО Тест",
    )
    tpl = EmailTemplate.objects.create(
        name="Реквизиты",
        subject="КП для {компания}",
        body="Здравствуйте, {имя}!",
    )
    EmailTemplate.objects.create(
        name="Выключенный",
        subject="off",
        body="off",
        is_active=False,
    )
    http = HttpClient()
    http.force_login(user)
    url = reverse("admin:crm_client_compose_email", args=[crm_client.pk])
    html = http.get(url, {"template": tpl.pk}).content.decode()
    assert 'value="КП для ООО Тест"' in html
    assert "Здравствуйте, Иван!" in html
    assert 'name="template"' in html
    assert "hoocon-mail-compose__template" in html
    assert "hoocon-mail-compose__apply" in html
    assert "Реквизиты" in html
    assert "Выключенный" not in html


@pytest.mark.django_db
def test_lead_compose_reply_prefills_from_template(django_user_model) -> None:
    """?template=<pk> overrides the default reply subject/body for a lead."""
    user = _superuser(django_user_model, "tpl-lead")
    lead = Lead.objects.create(
        name="Мария",
        email="maria@example.com",
        company="ООО Луч",
        message="Нужно КП на приводы",
    )
    tpl = EmailTemplate.objects.create(
        name="Уточнение",
        subject="Вопрос по заявке",
        body="{компания}, уточните объём.",
    )
    http = HttpClient()
    http.force_login(user)
    url = reverse("admin:leads_lead_compose_reply", args=[lead.pk])
    html = http.get(url, {"template": tpl.pk}).content.decode()
    assert 'value="Вопрос по заявке"' in html
    assert "ООО Луч, уточните объём." in html


@pytest.mark.django_db
def test_manager_group_gets_email_template_perms(django_user_model) -> None:
    """«Менеджер» группа: view/add/change шаблонов, без delete."""
    ensure_staff_groups()
    mgr = django_user_model.objects.create_user(
        username="tpl-mgr",
        password="pw",
        is_staff=True,
    )
    mgr.groups.add(Group.objects.get(name=GROUP_MANAGER))
    assert mgr.has_perm("crm.view_emailtemplate")
    assert mgr.has_perm("crm.add_emailtemplate")
    assert mgr.has_perm("crm.change_emailtemplate")
    assert not mgr.has_perm("crm.delete_emailtemplate")


def test_compose_template_picker_controls_are_shaped() -> None:
    """Список шаблонов и «Подставить» — скруглённые контролы в CSS страницы письма."""
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-mail-compose.css").read_text(
        encoding="utf-8"
    )
    select = css.split(".hoocon-mail-compose__template {", 1)[1].split("}", 1)[0]
    assert "appearance: none" in select
    assert "border-radius:" in select
    dark = css.split("html.dark .hoocon-mail-compose__template {", 1)[1].split("}", 1)[0]
    assert "color-scheme: dark" in dark
    apply = css.split(".hoocon-mail-compose__apply {", 1)[1].split("}", 1)[0]
    assert "height: 2rem" in apply
    assert "border-radius:" in apply
