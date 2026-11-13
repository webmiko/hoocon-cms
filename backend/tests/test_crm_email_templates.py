"""CRM email templates: model, placeholders, compose pickers, group perms."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse

from accounts.roles import GROUP_ADMIN, GROUP_ANALYST, GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Client, EmailTemplate
from crm.services import (
    email_template_context_for_client,
    email_template_context_for_lead,
    get_active_email_template,
    render_email_template,
)
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


def _group_user(django_user_model, username: str, group_name: str):
    """Staff member of one named group, not a superuser."""
    ensure_staff_groups()
    user = django_user_model.objects.create_user(username=username, password="x", is_staff=True, is_active=True)
    user.groups.add(Group.objects.get(name=group_name))
    return user


def _group_admin(django_user_model, username: str):
    """Staff in group «Админ», not a superuser."""
    return _group_user(django_user_model, username, GROUP_ADMIN)


def _manager(django_user_model, username: str):
    """Staff user in group «Менеджер»."""
    ensure_staff_groups()
    user = django_user_model.objects.create_user(username=username, password="x", is_staff=True, is_active=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


@pytest.mark.django_db
def test_author_only_template_is_hidden_from_other_managers(django_user_model) -> None:
    """Личный шаблон не виден коллеге в списке, в письме и по прямой ссылке на id."""
    author = _manager(django_user_model, "tpl-author")
    colleague = _manager(django_user_model, "tpl-other")
    private = EmailTemplate.objects.create(
        name="Личный черновик Людмилы",
        subject="Секретно {компания}",
        body="Текст только для автора.",
        visibility=EmailTemplate.Visibility.SELECTED,
        created_by=author,
    )
    private.visible_to.add(author)
    shared = EmailTemplate.objects.create(
        name="Общий шаблон",
        subject="Общая тема",
        body="Общий текст.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    lead = Lead.objects.create(
        name="Мария",
        email="maria-vis@example.com",
        company="ООО Луч",
        message="Нужно КП",
        status=Lead.LeadStatus.NEW,
    )
    http = HttpClient()
    compose = reverse("admin:leads_lead_compose_reply", args=[lead.pk])
    listing = reverse("admin:crm_emailtemplate_changelist")

    http.force_login(colleague)
    colleague_list = http.get(listing)
    assert colleague_list.status_code == 200
    colleague_html = colleague_list.content.decode()
    assert "Личный черновик Людмилы" not in colleague_html
    assert "Общий шаблон" in colleague_html
    hidden = http.get(compose, {"template": private.pk})
    assert hidden.status_code == 200
    hidden_html = hidden.content.decode()
    assert "Текст только для автора." not in hidden_html
    assert "Секретно" not in hidden_html
    assert "Личный черновик Людмилы" not in hidden_html
    assert "Общий шаблон" in hidden_html
    change_url = reverse("admin:crm_emailtemplate_change", args=[private.pk])
    change = http.get(change_url, follow=True)
    change_html = change.content.decode()
    assert "Текст только для автора." not in change_html
    assert "Личный черновик Людмилы" not in change_html
    stolen = http.post(
        change_url,
        {
            "name": "Перехвачено",
            "subject": "Чужая тема",
            "body": "Чужой текст.",
            "is_active": "on",
            "sort_order": "0",
            "visibility": EmailTemplate.Visibility.ALL,
        },
        follow=True,
    )
    assert "Чужой текст." not in stolen.content.decode()
    private.refresh_from_db()
    assert private.name == "Личный черновик Людмилы"
    assert private.body == "Текст только для автора."
    assert private.visibility == EmailTemplate.Visibility.SELECTED
    assert get_active_email_template(private.pk, colleague) is None
    assert get_active_email_template(private.pk) is None
    assert get_active_email_template(shared.pk, colleague) is not None

    http.force_login(author)
    own_list = http.get(listing).content.decode()
    assert "Личный черновик Людмилы" in own_list
    own_compose = http.get(compose, {"template": private.pk}).content.decode()
    assert "Текст только для автора." in own_compose
    assert "Личный черновик Людмилы" in own_compose
    assert get_active_email_template(private.pk, author) is not None


@pytest.mark.django_db
def test_manager_cannot_make_a_colleague_template_private(django_user_model) -> None:
    """Чужой общий шаблон нельзя сузить до себя."""
    author = _manager(django_user_model, "tpl-owner")
    colleague = _manager(django_user_model, "tpl-claimer")
    shared = EmailTemplate.objects.create(
        name="Общее письмо",
        subject="Тема",
        body="Текст общего письма.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    http = HttpClient()
    http.force_login(colleague)
    url = reverse("admin:crm_emailtemplate_change", args=[shared.pk])
    form_html = http.get(url).content.decode()
    assert 'name="audience_all" id="id_audience_all" value="1" checked disabled' in form_html
    assert '<input type="hidden" name="audience_all" value="1">' in form_html
    response = http.post(
        url,
        {
            "name": shared.name,
            "subject": shared.subject,
            "body": shared.body,
            "is_active": "on",
            "sort_order": "0",
            "audience": str(colleague.pk),
        },
    )
    assert response.status_code == 200
    assert "Круг людей меняет автор шаблона или администратор." in response.content.decode()
    shared.refresh_from_db()
    assert shared.visibility == EmailTemplate.Visibility.ALL
    assert shared.created_by_id == author.pk
    assert shared.body == "Текст общего письма."
    edited = http.post(url, _template_post(name=shared.name, subject=shared.subject, body="Уточнённый текст."))
    assert edited.status_code == 302
    shared.refresh_from_db()
    assert shared.body == "Уточнённый текст."
    assert shared.visibility == EmailTemplate.Visibility.ALL


@pytest.mark.django_db
def test_unscoped_staff_sees_author_only_template(django_user_model) -> None:
    """Администратор видит личный шаблон менеджера, чтобы его можно было найти."""
    author = _manager(django_user_model, "tpl-private-author")
    admin = _superuser(django_user_model, "tpl-private-admin")
    EmailTemplate.objects.create(
        name="Скрытый от менеджеров",
        subject="Тема",
        body="Личный текст.",
        visibility=EmailTemplate.Visibility.SELECTED,
        created_by=author,
    )
    EmailTemplate.objects.get(name="Скрытый от менеджеров").visible_to.add(author)
    http = HttpClient()
    http.force_login(admin)
    html = http.get(reverse("admin:crm_emailtemplate_changelist")).content.decode()
    assert "Скрытый от менеджеров" in html


def _named(django_user_model, username: str, first_name: str):
    """Manager with a visible first name."""
    user = _manager(django_user_model, username)
    user.first_name = first_name
    user.save(update_fields=["first_name"])
    return user


def _template_post(**overrides: object) -> dict[str, object]:
    """Changelist fields the template form always posts."""
    payload: dict[str, object] = {
        "name": "Письмо",
        "subject": "Тема",
        "body": "Текст письма.",
        "is_active": "on",
        "sort_order": "0",
        "audience_all": "1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_audience_field_lists_managers_and_everyone(django_user_model) -> None:
    """«Кому видно» — галочка «Всем» и действующие менеджеры, без «только автору»."""
    alena = _named(django_user_model, "tpl-alena", "Алёна")
    _named(django_user_model, "tpl-boris", "Борис")
    inactive = _named(django_user_model, "tpl-stas", "Стас")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    django_user_model.objects.create_user(
        username="tpl-super",
        password="x",
        first_name="Супер",
        is_staff=True,
        is_superuser=True,
    )
    http = HttpClient()
    http.force_login(alena)
    html = http.get(reverse("admin:crm_emailtemplate_add")).content.decode()
    assert "Только автору" not in html
    assert 'name="audience_all" id="id_audience_all" value="1" checked' in html
    assert "Алёна" in html
    assert "Борис" in html
    assert "Стас" not in html
    assert "Супер" not in html


@pytest.mark.django_db
def test_checked_managers_see_template_and_a_new_hire_does_not(django_user_model) -> None:
    """Снятое «Всем» оставляет шаблон отмеченным людям. Новый менеджер его не видит."""
    author = _named(django_user_model, "tpl-share-author", "Алёна")
    colleague = _named(django_user_model, "tpl-share-colleague", "Борис")
    outsider = _manager(django_user_model, "tpl-share-outsider")
    lead = Lead.objects.create(
        name="Мария",
        email="maria-share@example.com",
        company="ООО Луч",
        message="Нужно КП",
        status=Lead.LeadStatus.NEW,
    )
    http = HttpClient()
    http.force_login(author)
    saved = http.post(
        reverse("admin:crm_emailtemplate_add"),
        _template_post(
            name="Для двоих",
            body="Текст для двоих.",
            audience=[str(author.pk), str(colleague.pk)],
            audience_all="",
        ),
        follow=True,
    )
    assert saved.status_code == 200
    template = EmailTemplate.objects.get(name="Для двоих")
    assert template.visibility == EmailTemplate.Visibility.SELECTED
    assert template.created_by_id == author.pk
    assert set(template.visible_to.values_list("pk", flat=True)) == {author.pk, colleague.pk}
    change = http.get(reverse("admin:crm_emailtemplate_change", args=[template.pk]))
    change_html = change.content.decode()
    assert f'name="audience" id="id_audience_{author.pk}" value="{author.pk}" checked' in change_html
    assert 'name="audience_all" id="id_audience_all" value="1" checked' not in change_html
    compose = reverse("admin:leads_lead_compose_reply", args=[lead.pk])
    listing = reverse("admin:crm_emailtemplate_changelist")
    assert "Алёна, Борис" in http.get(listing).content.decode()

    http.force_login(colleague)
    assert "Для двоих" in http.get(listing).content.decode()
    assert "Текст для двоих." in http.get(compose, {"template": template.pk}).content.decode()

    hired = _manager(django_user_model, "tpl-share-hired")
    http.force_login(outsider)
    assert "Для двоих" not in http.get(listing).content.decode()
    assert "Текст для двоих." not in http.get(compose, {"template": template.pk}).content.decode()
    http.force_login(hired)
    assert "Для двоих" not in http.get(listing).content.decode()
    assert get_active_email_template(template.pk, hired) is None
    assert get_active_email_template(template.pk, colleague) is not None


@pytest.mark.django_db
def test_everyone_checkbox_includes_a_manager_hired_later(django_user_model) -> None:
    """«Всем» не замораживает текущий список: менеджер, принятый после сохранения, тоже видит шаблон."""
    author = _manager(django_user_model, "tpl-all-author")
    colleague = _manager(django_user_model, "tpl-all-colleague")
    template = EmailTemplate.objects.create(
        name="Общее на будущее",
        subject="Тема",
        body="Текст для всех.",
        visibility=EmailTemplate.Visibility.SELECTED,
        created_by=author,
    )
    template.visible_to.add(author)
    http = HttpClient()
    http.force_login(author)
    response = http.post(
        reverse("admin:crm_emailtemplate_change", args=[template.pk]),
        _template_post(name=template.name, body=template.body, audience=str(colleague.pk)),
    )
    assert response.status_code == 302
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL
    assert template.visible_to.count() == 0
    hired = _manager(django_user_model, "tpl-all-hired")
    assert get_active_email_template(template.pk, hired) is not None
    assert get_active_email_template(template.pk, colleague) is not None


@pytest.mark.django_db
def test_empty_audience_is_rejected(django_user_model) -> None:
    """Без «Всем» и без людей шаблон не становится невидимым."""
    author = _manager(django_user_model, "tpl-empty-author")
    template = EmailTemplate.objects.create(
        name="Не спрятать в никуда",
        subject="Тема",
        body="Текст остаётся общим.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    http = HttpClient()
    http.force_login(author)
    payload = _template_post(name=template.name, body=template.body)
    payload.pop("audience_all")
    response = http.post(reverse("admin:crm_emailtemplate_change", args=[template.pk]), payload)
    assert response.status_code == 200
    assert "хотя бы одного человека" in response.content.decode()
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL
    assert template.visible_to.count() == 0


@pytest.mark.django_db
def test_audience_rejects_a_user_who_is_not_a_manager(django_user_model) -> None:
    """В список нельзя подставить сотрудника не из группы «Менеджер»."""
    author = _manager(django_user_model, "tpl-staff-author")
    outsider = django_user_model.objects.create_user(
        username="tpl-not-manager",
        password="x",
        is_staff=True,
        is_active=True,
    )
    template = EmailTemplate.objects.create(
        name="Только менеджеры",
        subject="Тема",
        body="Текст.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    http = HttpClient()
    http.force_login(author)
    payload = _template_post(name=template.name, body=template.body, audience=str(outsider.pk))
    payload.pop("audience_all")
    response = http.post(reverse("admin:crm_emailtemplate_change", args=[template.pk]), payload)
    assert response.status_code == 200
    assert "действующие менеджеры" in response.content.decode()
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL
    assert outsider.pk not in set(template.visible_to.values_list("pk", flat=True))


@pytest.mark.django_db
def test_listed_manager_can_edit_text_but_not_the_audience(django_user_model) -> None:
    """Отмеченный коллега правит текст и не вычёркивает автора из списка."""
    author = _manager(django_user_model, "tpl-list-author")
    colleague = _manager(django_user_model, "tpl-list-colleague")
    template = EmailTemplate.objects.create(
        name="Общий черновик",
        subject="Тема",
        body="Исходный текст.",
        visibility=EmailTemplate.Visibility.SELECTED,
        created_by=author,
    )
    template.visible_to.set([author, colleague])
    http = HttpClient()
    http.force_login(colleague)
    url = reverse("admin:crm_emailtemplate_change", args=[template.pk])
    narrowed_payload = _template_post(name=template.name, body="Чужой захват.", audience=str(colleague.pk))
    narrowed_payload.pop("audience_all")
    narrowed = http.post(url, narrowed_payload)
    narrowed_html = narrowed.content.decode()
    assert narrowed.status_code == 200
    assert "Круг людей меняет автор шаблона или администратор." in narrowed_html
    template.refresh_from_db()
    assert template.body == "Исходный текст."
    assert set(template.visible_to.values_list("pk", flat=True)) == {author.pk, colleague.pk}

    edited_payload = _template_post(
        name=template.name,
        body="Поправленный текст.",
        audience=[str(author.pk), str(colleague.pk)],
    )
    edited_payload.pop("audience_all")
    edited = http.post(url, edited_payload)
    assert edited.status_code == 302
    template.refresh_from_db()
    assert template.body == "Поправленный текст."
    assert set(template.visible_to.values_list("pk", flat=True)) == {author.pk, colleague.pk}


@pytest.mark.django_db
def test_admin_can_limit_a_shared_template_that_has_no_author(django_user_model) -> None:
    """Общий шаблон без автора администратор отдаёт одному менеджеру, коллега — нет."""
    manager = _named(django_user_model, "tpl-assign-manager", "Алёна")
    admin = _superuser(django_user_model, "tpl-assign-admin")
    template = EmailTemplate.objects.create(
        name="Холодное письмо проектировщикам",
        subject="Приводы Hoocon для проекта {компания}",
        body="Текст холодного письма.",
        visibility=EmailTemplate.Visibility.ALL,
    )
    url = reverse("admin:crm_emailtemplate_change", args=[template.pk])
    http = HttpClient()
    http.force_login(manager)
    payload = _template_post(name=template.name, subject=template.subject, body=template.body)
    payload.pop("audience_all")
    payload["audience"] = str(manager.pk)
    refused = http.post(url, payload)
    assert refused.status_code == 200
    assert "Круг людей меняет автор шаблона или администратор." in refused.content.decode()
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL

    http.force_login(admin)
    saved = http.post(url, payload)
    assert saved.status_code == 302
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.SELECTED
    assert template.created_by_id is None
    assert list(template.visible_to.values_list("pk", flat=True)) == [manager.pk]


@pytest.mark.django_db
def test_admin_assigns_template_author_to_the_requesting_manager(django_user_model) -> None:
    """Админ создаёт шаблон по просьбе менеджера и указывает, кому он принадлежит."""
    owner = _named(django_user_model, "tpl-owner", "Алёна")
    colleague = _named(django_user_model, "tpl-not-owner", "Борис")
    admin = _group_admin(django_user_model, "tpl-author-admin")
    http = HttpClient()
    http.force_login(admin)
    add_url = reverse("admin:crm_emailtemplate_add")
    form_html = http.get(add_url).content.decode()
    assert 'name="created_by"' in form_html
    assert f'value="{owner.pk}"' in form_html
    created = http.post(
        add_url,
        _template_post(
            name="Письмо для Алёны",
            created_by=str(owner.pk),
            audience=str(owner.pk),
            audience_all="",
        ),
    )
    assert created.status_code == 302
    template = EmailTemplate.objects.get(name="Письмо для Алёны")
    assert template.created_by_id == owner.pk
    assert template.visibility == EmailTemplate.Visibility.SELECTED
    assert list(template.visible_to.values_list("pk", flat=True)) == [owner.pk]

    change_url = reverse("admin:crm_emailtemplate_change", args=[template.pk])
    http.force_login(owner)
    widened = _template_post(
        name=template.name,
        body=template.body,
        audience=[str(owner.pk), str(colleague.pk)],
    )
    widened.pop("audience_all")
    saved = http.post(change_url, widened)
    assert saved.status_code == 302
    template.refresh_from_db()
    assert template.created_by_id == owner.pk
    assert set(template.visible_to.values_list("pk", flat=True)) == {owner.pk, colleague.pk}

    http.force_login(colleague)
    stolen = _template_post(name=template.name, body=template.body, created_by=str(colleague.pk))
    refused = http.post(change_url, stolen)
    template.refresh_from_db()
    assert template.created_by_id == owner.pk
    assert 'name="created_by"' not in http.get(change_url).content.decode()
    assert refused.status_code in {200, 302}


@pytest.mark.django_db
def test_analyst_cannot_rewrite_template_audience(django_user_model) -> None:
    """Аналитик видит все шаблоны, но не меняет, кому они видны."""
    author = _named(django_user_model, "tpl-analyst-author", "Алёна")
    analyst = _group_user(django_user_model, "tpl-analyst", GROUP_ANALYST)
    template = EmailTemplate.objects.create(
        name="Общий для аналитика",
        subject="Тема",
        body="Текст.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    http = HttpClient()
    http.force_login(analyst)
    url = reverse("admin:crm_emailtemplate_change", args=[template.pk])
    payload = _template_post(name=template.name, subject=template.subject, body=template.body)
    payload.pop("audience_all")
    payload["audience"] = str(author.pk)
    response = http.post(url, payload)
    assert response.status_code == 403
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL
    assert template.visible_to.count() == 0


@pytest.mark.django_db
def test_analyst_with_change_perm_still_cannot_narrow_audience(django_user_model) -> None:
    """Даже с правом править шаблон аналитик не сужает чужой список."""
    from django.contrib.auth.models import Permission

    author = _named(django_user_model, "tpl-analyst-change-author", "Алёна")
    analyst = _group_user(django_user_model, "tpl-analyst-change", GROUP_ANALYST)
    perm = Permission.objects.get(codename="change_emailtemplate", content_type__app_label="crm")
    analyst.user_permissions.add(perm)
    template = EmailTemplate.objects.create(
        name="Общий при лишнем праве",
        subject="Тема",
        body="Текст.",
        visibility=EmailTemplate.Visibility.ALL,
        created_by=author,
    )
    http = HttpClient()
    http.force_login(analyst)
    url = reverse("admin:crm_emailtemplate_change", args=[template.pk])
    payload = _template_post(name=template.name, subject=template.subject, body=template.body)
    payload.pop("audience_all")
    payload["audience"] = str(author.pk)
    response = http.post(url, payload)
    assert response.status_code == 200
    assert "Круг людей меняет автор шаблона или администратор." in response.content.decode()
    template.refresh_from_db()
    assert template.visibility == EmailTemplate.Visibility.ALL
    assert template.visible_to.count() == 0


@pytest.mark.django_db
def test_legacy_author_flag_becomes_that_manager(django_user_model) -> None:
    """Старое «только автору» с заполненным автором видно ему; без автора шаблон остаётся общим."""
    import importlib

    from django.apps import apps

    migration = importlib.import_module("crm.migrations.0026_emailtemplate_audience")
    author = _manager(django_user_model, "tpl-legacy-author")
    colleague = _manager(django_user_model, "tpl-legacy-colleague")
    named = EmailTemplate.objects.create(
        name="Старый личный",
        subject="Тема",
        body="Личный текст.",
        visibility="author",
        created_by=author,
    )
    orphan = EmailTemplate.objects.create(
        name="Старый без автора",
        subject="Тема",
        body="Общий текст.",
        visibility="author",
    )
    migration.convert_author_only_templates(apps, None)
    named.refresh_from_db()
    orphan.refresh_from_db()
    assert named.visibility == EmailTemplate.Visibility.SELECTED
    assert list(named.visible_to.values_list("pk", flat=True)) == [author.pk]
    assert orphan.visibility == EmailTemplate.Visibility.ALL
    assert orphan.visible_to.count() == 0
    assert get_active_email_template(named.pk, author) is not None
    assert get_active_email_template(named.pk, colleague) is None
    assert get_active_email_template(orphan.pk, colleague) is not None


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
