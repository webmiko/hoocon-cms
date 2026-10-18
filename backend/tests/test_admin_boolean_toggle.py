"""Admin booleans use the integrations toggle; row picks stay checkboxes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import models
from django.test import Client
from django.urls import reverse

from catalog.models import SKU, AnalogMap, Attribute, AttributeValue, Category, Product
from config.admin_toggle import HooconToggleInput
from crm.models import Company, CompanyMember
from leads.models import CompanyManagerRule, Lead
from supportchat.models import (
    Channel,
    Conversation,
    SupportSchedule,
    SupportScheduleDay,
)

_BACKEND = Path(__file__).resolve().parents[1]
_EXTRAS = _BACKEND / "static/admin/css/hoocon-unfold-extras.css"


def _css_rule(css: str, selector: str) -> str:
    """Return the declaration block for an exact selector, or '' if absent."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return match.group(1) if match else ""


def test_toggle_css_swaps_caption_with_state() -> None:
    """Caption switch lives in hoocon-unfold-extras.css — the file Unfold loads.

    Locks the mechanism, not just selectors: both captions start hidden,
    --off is shown while unchecked, :checked hides --off and shows --on.
    """
    css = _EXTRAS.read_text(encoding="utf-8")
    assert "display: none" in _css_rule(css, ".hoocon-bool-toggle__state")
    assert "display: inline" in _css_rule(css, ".hoocon-bool-toggle__state--off")
    assert "display: none" in _css_rule(
        css,
        ".hoocon-bool-toggle:has(input:checked) .hoocon-bool-toggle__state--off",
    )
    assert "display: inline" in _css_rule(
        css,
        ".hoocon-bool-toggle:has(input:checked) .hoocon-bool-toggle__state--on",
    )


def test_toggle_widget_renders_both_captions_and_keeps_checkbox_value() -> None:
    """Captions come from ``labels``; the submitted value is still a plain checkbox."""
    default = HooconToggleInput().render("flag", True)
    assert "Выключено" in default
    assert "Включено" in default
    assert "checked" in default

    custom = HooconToggleInput(labels=("STARTTLS", "SSL")).render("form-0-smtp_use_ssl", False)
    assert "STARTTLS" in custom
    assert ">SSL<" in custom
    assert "checked" not in custom

    widget = HooconToggleInput()
    assert widget.value_from_datadict({"flag": "on"}, {}, "flag") is True
    assert widget.value_from_datadict({}, {}, "flag") is False


def test_toggle_captions_do_not_leak_by_field_name() -> None:
    """A field that merely shares a name with a captioned one keeps the default captions."""
    html = HooconToggleInput().render("send_now", True)
    assert "Отправить сразу" not in html
    assert "Включено" in html


def test_no_nullable_boolean_fields_in_project_models() -> None:
    """The switch has two states, so a ``null=True`` boolean would lose ``None`` on save.

    Only this project's apps: a third-party model is not ours to change.
    """
    nullable = [
        f"{model._meta.label}.{field.name}"
        for config in apps.get_app_configs()
        if Path(config.path).resolve().is_relative_to(_BACKEND) and ".venv" not in Path(config.path).parts
        for model in config.get_models()
        for field in model._meta.get_fields()
        if isinstance(field, models.BooleanField) and field.null
    ]
    assert nullable == []


@pytest.mark.django_db
def test_state_flags_render_meaningful_captions(client, django_user_model) -> None:
    """State flags keep the switch but get per-field captions, not «Вкл/Выкл».

    Locks each surface: contact_verified ×2, is_closed (own page + inline),
    is_confirmed inline, copy_locked ×2, is_manual inline, spring_return,
    exclusive. Captions are bound to the field's own toggle: two fields with
    equal captions on one page are still told apart.
    """
    user = django_user_model.objects.create_superuser(
        username="cap",
        email="cap@hoocon.ru",
        password="pw12345678",
    )
    client.force_login(user)

    lead = Lead.objects.create(
        lead_type="rfq",
        name="Иван",
        email="ivan@cap.test",
        company="ООО Тест",
        message="Нужен КП на десять позиций.",
    )
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="s-cap")
    # SupportSchedule — singleton pk=1; days seeded per weekday.
    schedule = SupportSchedule.objects.get_or_create(pk=1)[0]
    day = SupportScheduleDay.objects.get_or_create(schedule=schedule, weekday=0)[0]
    category = Category.objects.create(name="C", slug="c-cap")
    product = Product.objects.create(category=category, name="P", slug="p-cap")
    sku = SKU.objects.create(product=product, name="S", slug="s-cap", sku_code="SKU-CAP")
    attr = Attribute.objects.create(name="Момент", slug="moment-cap")
    AttributeValue.objects.create(sku=sku, attribute=attr, value="10")
    amap = AnalogMap.objects.create(brand="B", foreign_code="X-1", sku=sku)
    # Имя, отличное от компании заявки: сигнал лида уже создал карточку «ООО Тест».
    company = Company.objects.create(name="ООО Участники")
    CompanyMember.objects.create(company=company)
    rule = CompanyManagerRule.objects.create(company_label="ООО Акме", assignee=user)

    checks = [
        # url_name, pk, query, field name (inline names carry a prefix), off, on
        ("leads_lead_change", lead.pk, "?edit=1", "contact_verified", "Не подтверждён", "Подтверждён"),
        ("supportchat_conversation_change", conv.pk, "", "contact_verified", "Не подтверждён", "Подтверждён"),
        ("supportchat_supportschedule_change", schedule.pk, "", "is_closed", "Рабочий день", "Выходной"),
        ("supportchat_supportscheduleday_change", day.pk, "", "is_closed", "Рабочий день", "Выходной"),
        ("catalog_product_change", product.pk, "", "copy_locked", "Из мануала", "Правлены вручную"),
        ("catalog_sku_change", sku.pk, "", "copy_locked", "Из мануала", "Правлены вручную"),
        ("catalog_sku_change", sku.pk, "", "is_manual", "Из мануала", "Правлено вручную"),
        ("catalog_analogmap_change", amap.pk, "", "spring_return", "Нет", "Есть"),
        ("crm_company_change", company.pk, "", "is_confirmed", "Не подтверждён", "Подтверждён"),
        ("leads_companymanagerrule_change", rule.pk, "", "exclusive", "В общей очереди", "Только закреплённые"),
    ]
    for url_name, pk, query, field, off, on in checks:
        html = client.get(reverse(f"admin:{url_name}", args=[pk]) + query).content.decode()
        toggle = re.search(
            rf'<label class="hoocon-bool-toggle"><input[^>]*name="[^"]*{field}"[^>]*>(.*?)</label>',
            html,
            re.S,
        )
        assert toggle is not None, f"{url_name}: {field} toggle missing"
        assert f'--off">{off}</span>' in toggle.group(1), f"{url_name}: {field} off caption"
        assert f'--on">{on}</span>' in toggle.group(1), f"{url_name}: {field} on caption"


@pytest.mark.django_db
def test_labeled_toggles_carry_aria_label() -> None:
    """Tabular inlines keep the field name in <th>, so the switch must name itself.

    The state caption changes with the position and cannot be the accessible
    name; ``aria-label`` is the field's ``verbose_name``.
    """
    user = User.objects.create_superuser(username="aria", email="aria@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)

    schedule = SupportSchedule.objects.get_or_create(pk=1)[0]
    SupportScheduleDay.objects.get_or_create(schedule=schedule, weekday=0)
    company = Company.objects.create(name="ООО Диктор")
    CompanyMember.objects.create(company=company)

    checks = [
        ("supportchat_supportschedule_change", schedule.pk, "is_closed", "Выходной"),
        ("crm_company_change", company.pk, "is_confirmed", "Подтверждён менеджером"),
    ]
    for url_name, pk, field, label in checks:
        html = client.get(reverse(f"admin:{url_name}", args=[pk])).content.decode()
        toggle = re.search(
            rf'<input(?=[^>]*name="[^"]*{field}")(?=[^>]*aria-label="{label}")[^>]*>',
            html,
        )
        assert toggle is not None, f"{url_name}: {field} aria-label"


@pytest.mark.django_db
def test_every_admin_toggle_has_aria_label() -> None:
    """Toggles without custom captions are named too: SKU gallery and files, the staff card."""
    user = User.objects.create_superuser(username="aria-all", email="aria-all@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)
    category = Category.objects.create(name="C", slug="c-aria")
    product = Product.objects.create(category=category, name="P", slug="p-aria")
    sku = SKU.objects.create(product=product, name="S", slug="s-aria", sku_code="SKU-ARIA")

    pages = [
        reverse("admin:catalog_sku_change", args=[sku.pk]),
        reverse("admin:catalog_product_change", args=[product.pk]),
        reverse("admin:auth_user_change", args=[user.pk]),
    ]
    for url in pages:
        html = client.get(url).content.decode()
        toggles = re.findall(r'<input(?=[^>]*class="hoocon-toggle)[^>]*>', html)
        assert toggles, url
        unnamed = [tag for tag in toggles if "aria-label=" not in tag]
        assert unnamed == [], url
    sku_html = client.get(pages[0]).content.decode()
    published = re.search(r'<input(?=[^>]*name="[^"]*-is_published")[^>]*>', sku_html)
    assert published is not None
    assert 'aria-label="' in published.group(0)


def test_toggle_field_keeps_explicit_aria_label() -> None:
    """A form that names its switch itself (send_now) is not overwritten by the label."""
    from config.admin_toggle import ToggleBooleanField

    field = ToggleBooleanField(label="Флаг", widget=HooconToggleInput(attrs={"aria-label": "Своё"}))
    assert field.widget.attrs["aria-label"] == "Своё"
    assert ToggleBooleanField(label="Флаг", widget=HooconToggleInput).widget.attrs["aria-label"] == "Флаг"


@pytest.mark.django_db
def test_staff_profile_booleans_are_toggles_with_captions() -> None:
    """Profile flags and the account switches show Выключено/Включено, not a bare checkbox."""
    user = User.objects.create_superuser(username="toggle-admin", email="toggle@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)
    html = client.get(reverse("admin:auth_user_change", args=[user.pk])).content.decode()

    # Inline flags without Meta.widgets: only install_admin_boolean_toggles makes these switches.
    for field in (
        "telegram_profile-0-telegram_alerts_enabled",
        "max_profile-0-max_alerts_enabled",
        "vpbx_profile-0-is_enabled",
    ):
        inline = re.search(
            rf'<label class="hoocon-bool-toggle"><input(?=[^>]*class="hoocon-toggle")[^>]*name="{field}"',
            html,
        )
        assert inline is not None, field
    main_form = re.search(
        r'<label class="hoocon-bool-toggle"><input[^>]*id="id_is_superuser"',
        html,
    )
    assert main_form is not None
    assert "Выключено" in html
    assert "Включено" in html
    assert "STARTTLS" in html
    assert ">SSL<" in html
    clear = re.search(r"<input\b[^>]*clear_uis_webrtc_token[^>]*>", html)
    assert clear is not None
    assert "hoocon-toggle" not in clear.group(0)


@pytest.mark.django_db
def test_changelist_row_picker_stays_a_checkbox() -> None:
    """«Выберите запись» is a multi-select, so it does not become a switch."""
    user = User.objects.create_superuser(username="toggle-list", email="list@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)
    html = client.get(reverse("admin:auth_user_changelist")).content.decode()
    picker = html.split('name="_selected_action"', 1)[0][-500:]
    assert "hoocon-bool-toggle" not in picker
