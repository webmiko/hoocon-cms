"""CRM email templates: model, placeholders, compose pickers, group perms."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Client, EmailTemplate
from crm.services import email_template_context_for_client, render_email_template
from leads.models import Lead


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
    }


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
