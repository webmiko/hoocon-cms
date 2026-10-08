"""Tests for Russian Admin labels (apps, models, branding, no English UI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from config.ru_ui_lint import (
    PROJECT_APP_LABELS,
    find_unexpected_english_in_html,
    iter_admin_ui_strings,
    iter_model_ui_strings,
    unexpected_latin_tokens,
)
from supportchat.models import FaqItem

User = get_user_model()

_EXPECTED_APP_NAMES = {
    "accounts": "Учётные записи / роли",
    "catalog": "Каталог",
    "content": "Контент",
    "leads": "Заявки",
    "crm": "CRM / клиенты",
    "redirects": "Редиректы",
    "sitesettings": "Настройки сайта",
    "social": "Соцсети / анонсы",
    "axes": "Защита входа",
    "django_celery_beat": "Периодические задачи",
}


@pytest.mark.parametrize(("label", "name"), sorted(_EXPECTED_APP_NAMES.items()))
def test_admin_app_verbose_name_is_russian(label: str, name: str) -> None:
    """Project and key third-party apps show Russian names in Admin index."""
    assert apps.get_app_config(label).verbose_name == name


@pytest.mark.django_db
def test_admin_index_has_no_english_app_headings() -> None:
    """Admin dashboard does not show English app group titles."""
    admin_user = User.objects.create_superuser(
        username="admin-ru",
        email="admin-ru@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()

    assert "Каталог" in html
    assert "Контент" in html
    assert "Заявки" in html
    assert "Редиректы" in html
    assert "Настройки сайта" in html
    assert "Защита входа" in html
    assert "HOOCON CMS" in html or "Панель управления" in html

    # App captions / module headings (avoid false positives like <!-- Content -->).
    for english in (
        ">Catalog<",
        ">Content<",
        ">Leads<",
        ">Redirects<",
        ">Sitesettings<",
        ">Axes<",
    ):
        assert english not in html


def test_sku_model_verbose_name_is_russian() -> None:
    """SKU model uses Russian verbose_name in Admin."""
    sku = apps.get_model("catalog", "SKU")
    assert "артикул" in str(sku._meta.verbose_name).lower()
    assert "SKU" in str(sku._meta.verbose_name)


def test_locale_middleware_is_enabled() -> None:
    """LocaleMiddleware activates Django's Russian admin translations."""
    from django.conf import settings

    assert "django.middleware.locale.LocaleMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
def test_sku_changelist_has_open_button() -> None:
    """SKU list shows «Открыть» so cards need no ID click."""
    from catalog.models import SKU, Category, Product

    admin_user = User.objects.create_superuser(
        username="admin-open",
        email="admin-open@example.com",
        password="password12",
    )
    cat = Category.objects.create(name="Cat", slug="cat-open")
    product = Product.objects.create(name="Prod", slug="prod-open", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SKU Open",
        slug="sku-open-test",
        sku_code="OPEN-1",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/catalog/sku/").content.decode()
    assert "Открыть" in html
    assert f"/admin/catalog/sku/{sku.pk}/change/" in html
    assert "Артикулы" in client.get("/admin/").content.decode()


def test_project_ui_strings_have_no_unexpected_english() -> None:
    """Model/Admin RU labels must not leak English words (allowlist only).

    Catches developer English in verbose_name / help_text / choices /
    fieldset copy so managers see a fully Russian Admin.
    """
    failures: list[str] = []

    for model in apps.get_models():
        if model._meta.app_label not in PROJECT_APP_LABELS:
            continue
        for where, text in iter_model_ui_strings(model):
            bad = unexpected_latin_tokens(text)
            if bad:
                failures.append(f"{where}: {bad!r} in {text!r}")

    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label not in PROJECT_APP_LABELS:
            continue
        for where, text in iter_admin_ui_strings(model_admin, model):
            bad = unexpected_latin_tokens(text)
            if bad:
                failures.append(f"{where}: {bad!r} in {text!r}")

    assert not failures, "English leftovers in RU Admin UI:\n" + "\n".join(failures)


@pytest.mark.django_db
def test_faqitem_changelist_has_no_english_ui_strings() -> None:
    """FAQ changelist labels and hints must stay Russian (no Inbox/Select record)."""
    admin_user = User.objects.create_superuser(
        username="admin-faq-ru",
        email="admin-faq-ru@example.com",
        password="password12",
    )
    FaqItem.objects.create(
        question="SA вместо DA?",
        answer="Серия SA — для регулирования; DA — для полного открытия/закрытия.",
        order=1,
        is_active=True,
        show_in_chat=True,
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/supportchat/faqitem/").content.decode()

    assert "SA вместо DA?" in html
    assert "частые вопросы чата" in html or "вопрос чата" in html

    start = html.find('id="changelist-form"')
    end = html.find("</form>", start)
    changelist_html = html[start:end] if start >= 0 and end > start else html

    html_failures = find_unexpected_english_in_html(changelist_html)
    assert not html_failures, "English UI on FAQ changelist:\n" + "\n".join(html_failures)

    for english in (
        ">Inbox<",
        "Select record",
        "Type to search",
        "Search apps and models",
        "Select action",
        ">Add FAQ",
        ">Delete selected",
    ):
        assert english not in changelist_html

    assert "form-0-answer" not in changelist_html
    assert "Серия SA — для регулирования" in changelist_html


@pytest.mark.django_db
def test_faqitem_changelist_does_not_inline_edit_answer() -> None:
    """Long FAQ answers are edited on the change form, not the stacked list."""
    admin_user = User.objects.create_superuser(
        username="admin-faq-inline",
        email="admin-faq-inline@example.com",
        password="password12",
    )
    item = FaqItem.objects.create(
        question="SA вместо DA?",
        answer="Старый ответ",
        order=1,
        is_active=True,
        show_in_chat=True,
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/supportchat/faqitem/").content.decode()
    assert "form-0-answer" not in html

    response = client.post(
        reverse("admin:supportchat_faqitem_change", args=[item.pk]),
        {
            "question": "SA вместо DA?",
            "question_short": "",
            "answer": "Новый ответ в карточке",
            "order": "1",
            "is_active": "on",
            "show_in_chat": "on",
            "show_on_home": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.answer == "Новый ответ в карточке"


def test_tables_js_overrides_prefilled_select_record_label() -> None:
    """Stacked cards must replace Unfold's English checkbox data-label."""
    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-tables.js").read_text(encoding="utf-8")
    assert 'const CHECKBOX_LABEL = "Выберите запись"' in js
    assert 'cell.setAttribute("data-label", CHECKBOX_LABEL)' in js
    checkbox_block = js[js.find("function applyRowLabels") : js.find("function markBlankCells")]
    assert 'cell.classList.contains("action-checkbox")' in checkbox_block
    assert 'getAttribute("data-label")' in checkbox_block


def test_every_admin_changelist_explains_empty_section() -> None:
    """Each registered admin list has a Russian explanation of the section."""
    from django.contrib import admin

    from config.empty_state import EMPTY_STATE_HELP, empty_state_help_for

    labels = {model._meta.label for model in admin.site._registry}
    missing = [
        model._meta.label
        for model, model_admin in admin.site._registry.items()
        if not empty_state_help_for(model_admin).strip()
    ]
    assert missing == []
    assert set(EMPTY_STATE_HELP) == labels


@pytest.mark.django_db
def test_company_empty_changelist_explains_the_section() -> None:
    """Empty «Компании» list explains the section instead of the generic stub."""
    from crm.models import Company

    Company.objects.all().delete()
    admin_user = User.objects.create_superuser(
        username="admin-company-empty",
        email="admin-company-empty@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/crm/company/").content.decode()
    assert "Юрлицо заказчика" in html
    assert "поля «Компания»" in html
    assert "На этой странице нет результатов" not in html


@pytest.mark.django_db
def test_company_search_miss_keeps_generic_empty_hint() -> None:
    """Search with no hits keeps the reset hint, not the section explanation."""
    admin_user = User.objects.create_superuser(
        username="admin-company-search",
        email="admin-company-search@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/crm/company/?q=нет-такой-компании-xyz").content.decode()
    assert "На этой странице нет результатов" in html
    assert "Юрлицо заказчика" not in html


def test_unfold_empty_results_strings_russian() -> None:
    """Unfold's empty-changelist strings resolve to Russian via project locale."""
    from django.utils import translation
    from django.utils.translation import gettext

    with translation.override("ru"):
        assert gettext("No results found") == "Ничего не найдено"
        assert gettext("Reset filters") == "Сбросить фильтры"
        assert (
            gettext("This page yielded into no results. Create a new item or reset your filters.")
            == "На этой странице нет результатов. Создайте запись или сбросьте фильтры."
        )
