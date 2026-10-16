"""Telephony widgets: Mango and Novosystem can be switched from Admin."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from django.urls import reverse

from crm.models import Call


def _signed(payload: dict[str, Any], *, key: str = "test-key", salt: str = "test-salt") -> dict[str, str]:
    raw = json.dumps(payload, ensure_ascii=False)
    sign = hashlib.sha256(f"{key}{raw}{salt}".encode()).hexdigest()
    return {"vpbx_api_key": key, "json": raw, "sign": sign}


@pytest.mark.django_db
def test_mango_widget_off_rejects_signed_webhook(client: Any, settings: Any) -> None:
    """Выключенный виджет Mango закрывает вебхук, даже если ключи в окружении верные."""
    from sitesettings.models import SiteSettings

    settings.MANGO_VPBX_API_KEY = "test-key"
    settings.MANGO_VPBX_API_SALT = "test-salt"
    site = SiteSettings.load()
    site.mango_enabled = False
    site.save()
    payload = {
        "entry_id": "entry-off",
        "call_id": "call-off",
        "seq": 1,
        "call_state": "Appeared",
        "from": {"number": "79151112233"},
        "to": {"extension": "101"},
    }
    response = client.post("/api/telephony/mango/events/", _signed(payload))
    assert response.status_code == 403
    assert Call.objects.filter(entry_id="entry-off").count() == 0


@pytest.mark.django_db
def test_mango_admin_key_overrides_env(settings: Any) -> None:
    """Ключ из виджета важнее MANGO_VPBX_API_KEY."""
    from sitesettings.models import SiteSettings
    from sitesettings.telephony import mango_settings

    settings.MANGO_VPBX_API_KEY = "env-key"
    settings.MANGO_VPBX_API_SALT = "env-salt"
    site = SiteSettings.load()
    site.mango_api_key = "admin-key"
    site.mango_api_salt = ""
    site.save()
    enabled, key, salt, _callback = mango_settings()
    assert enabled is True
    assert key == "admin-key"
    assert salt == "env-salt"


@pytest.mark.django_db
def test_telephony_widget_save_keeps_blank_secret(client: Any, django_user_model: Any) -> None:
    """Пустой секрет в форме виджета не затирает уже сохранённый ключ."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_access_token = "keep-me"
    site.novosystem_enabled = False
    site.save()
    user = django_user_model.objects.create_superuser(
        username="pbx-widget",
        email="pbx-widget@example.com",
        password="password12",
    )
    client.force_login(user)
    response = client.post(
        reverse("admin:sitesettings_telephony_widget"),
        {
            "provider": "novosystem",
            "novosystem_enabled": "on",
            "novosystem_access_token": "",
            "novosystem_virtual_phone": "74951234567",
            "novosystem_webhook_secret": "hook-secret",
        },
    )
    assert response.status_code == 302
    site.refresh_from_db()
    assert site.novosystem_enabled is True
    assert site.novosystem_access_token == "keep-me"
    assert site.novosystem_virtual_phone == "74951234567"
    assert site.novosystem_webhook_secret == "hook-secret"


@pytest.mark.django_db
def test_saved_telephony_secrets_look_filled_but_stay_hidden(client: Any, django_user_model: Any) -> None:
    """Заданные ключ и секрет рисуются точками. Повтор точек не подменяет сохранённое."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_access_token = "live-api-token"
    site.novosystem_webhook_secret = "live-hook-secret"
    site.novosystem_virtual_phone = "74951234567"
    site.save()
    user = django_user_model.objects.create_superuser(
        username="pbx-dots",
        email="pbx-dots@example.com",
        password="password12",
    )
    client.force_login(user)
    html = client.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    assert html.count('value="••••••••••••"') == 2
    assert 'value="live-api-token"' not in html
    assert 'value="live-hook-secret"' not in html
    assert "не задан" in html
    response = client.post(
        reverse("admin:sitesettings_telephony_widget"),
        {
            "provider": "novosystem",
            "novosystem_access_token": "••••••••••••",
            "novosystem_webhook_secret": "••••••••••••",
            "novosystem_virtual_phone": "74951234567",
        },
    )
    assert response.status_code == 302
    site.refresh_from_db()
    assert site.novosystem_access_token == "live-api-token"
    assert site.novosystem_webhook_secret == "live-hook-secret"


@pytest.mark.django_db
def test_novosystem_webhook_stores_call_only_when_enabled(client: Any) -> None:
    """Вебхук UIS создаёт звонок только у включённого виджета с верным секретом."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_enabled = False
    site.novosystem_webhook_secret = "hook-secret"
    site.save()
    body = {
        "call_session_id": "9001",
        "direction": "in",
        "contact_phone_number": "79161112233",
        "token": "hook-secret",
    }
    assert client.post("/api/telephony/novosystem/events/", body, content_type="application/json").status_code == 403

    site.novosystem_enabled = True
    site.save()
    response = client.post("/api/telephony/novosystem/events/", body, content_type="application/json")
    assert response.status_code == 200
    call = Call.objects.get(entry_id="uis:9001")
    assert call.from_number.endswith("9161112233") or "9161112233" in call.from_number


@pytest.mark.django_db
def test_integrations_page_renders_telephony_widgets(client: Any, django_user_model: Any) -> None:
    """Страница интеграций показывает только виджет Новосистем."""
    from sitesettings.models import SiteSettings

    SiteSettings.load()
    user = django_user_model.objects.create_superuser(
        username="pbx-page",
        email="pbx-page@example.com",
        password="password12",
    )
    client.force_login(user)
    html = client.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    assert 'id="telephony-novosystem"' in html
    assert 'id="telephony-mango"' not in html
    assert "Mango" not in html
    assert html.count("hoocon-pbx__widget hoocon-integrations__card") == 1
    assert '<form class="hoocon-pbx__widget' not in html
    assert html.count('hoocon-pbx__state--on">Виджет включён') == 1
    assert html.count('hoocon-pbx__state--off">Виджет выключен') == 1
    assert html.count('hoocon-pbx__state--partial">Не полностью') == 1
    assert html.count('type="checkbox" class="hoocon-toggle" name="novosystem_enabled"') == 1
    assert "/api/telephony/novosystem/events/" in html
    assert "hoocon-pbx__save" in html
    site = SiteSettings.load()
    change = client.get(reverse("admin:sitesettings_sitesettings_change", args=[site.pk])).content.decode()
    assert "Mango" not in change
    assert "mango_" not in change
    from crm.models import Call

    call = Call.objects.create(entry_id="uis:admin-label", from_number="74950000000", to_number="74950000001")
    call_html = client.get(reverse("admin:crm_call_change", args=[call.pk])).content.decode()
    assert "Mango" not in call_html
    assert "ID вызова" in call_html
    user_html = client.get(reverse("admin:auth_user_change", args=[user.pk])).content.decode()
    assert "Mango" not in user_html


def test_telephony_save_buttons_pinned_to_card_bottom() -> None:
    """Кнопка «Сохранить» виджета телефонии стоит внизу карточки."""
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8"
    )

    def rule(selector: str) -> str:
        match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", css)
        assert match, selector
        return match.group(1)

    assert "align-items: stretch" in rule(".hoocon-widget-grid")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css.split(".hoocon-widget-grid {", 2)[2]
    joined = css.split(".hoocon-pbx,", 1)[1].split("}", 1)[0]
    assert "display: contents" in joined
    assert ".hoocon-staffreq-list" in joined
    widget = rule(".hoocon-pbx__widget")
    assert "display: flex" in widget
    assert "flex-direction: column" in widget
    assert "margin-top: auto" in rule(".hoocon-pbx__save")
    assert "display: none" in rule(".hoocon-pbx__state")
    assert ".hoocon-pbx__toggle:has(input:checked) .hoocon-pbx__state--off" in css
    assert "hoocon-pbx__widget--ready .hoocon-pbx__toggle:has(input:checked) .hoocon-pbx__state--on" in css


def _enable_uis(*, secret: str = "hook-secret", token: str = "uis-token", phone: str = "74951234567") -> None:
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_enabled = True
    site.novosystem_webhook_secret = secret
    site.novosystem_access_token = token
    site.novosystem_virtual_phone = phone
    site.save()


@pytest.mark.django_db
def test_novosystem_webhook_keeps_manager_time_and_finished_state(client: Any, django_user_model: Any) -> None:
    """UIS: менеджер по employee_id, время звонка, лента один раз, повтор не открывает звонок."""
    from django.utils import timezone

    from accounts.models import StaffVpbxProfile
    from crm.models import Activity, ActivityType, Client
    from leads.models import Lead

    _enable_uis()
    owner = django_user_model.objects.create_user(username="uis-owner", email="owner@example.com")
    other = django_user_model.objects.create_user(username="uis-other", email="other@example.com")
    StaffVpbxProfile.objects.create(user=owner, extension="300", uis_employee_id="77")
    StaffVpbxProfile.objects.create(user=other, extension="101", uis_employee_id="88")
    crm_client = Client.objects.create(email="buyer@example.com", name="Buyer", phone="79161112233")
    lead = Lead.objects.create(name="Buyer", email="buyer@example.com", message="нужен привод", client=crm_client)
    body = {
        "token": "hook-secret",
        "call_session_id": "9002",
        "direction": "out",
        "contact_phone_number": "+7 (916) 111-22-33",
        "employee_id": 77,
        "extension": "101",
        "start_time": "2024-03-01 10:15:00",
        "finish_time": "2024-03-01 10:16:00",
        "talk_duration": "40",
    }
    assert client.post("/api/telephony/novosystem/events/", body, content_type="application/json").status_code == 200
    call = Call.objects.get(entry_id="uis:9002")
    assert call.manager_id == owner.pk
    assert call.client_id == crm_client.pk
    assert call.lead_id == lead.pk
    assert call.state == "disconnected"
    local_start = timezone.localtime(call.started_at)
    assert (local_start.year, local_start.month, local_start.day, local_start.hour, local_start.minute) == (
        2024,
        3,
        1,
        10,
        15,
    )
    assert Activity.objects.filter(client=crm_client, activity_type=ActivityType.CALL).count() == 1

    replay = {key: value for key, value in body.items() if key != "finish_time"}
    replay["talk_duration"] = "0"
    assert client.post("/api/telephony/novosystem/events/", replay, content_type="application/json").status_code == 200
    call.refresh_from_db()
    assert call.state == "disconnected"
    assert call.talk_duration == 40
    assert Activity.objects.filter(client=crm_client, activity_type=ActivityType.CALL).count() == 1


@pytest.mark.django_db
def test_uis_click_to_call_skips_short_extension_and_mango(
    client: Any,
    django_user_model: Any,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При включённом Mango звонок идёт в UIS, если у менеджера есть только ID сотрудника."""
    import io
    import urllib.request

    from accounts.models import StaffVpbxProfile
    from crm.models import Client

    settings.MANGO_VPBX_API_KEY = "env-key"
    settings.MANGO_VPBX_API_SALT = "env-salt"
    _enable_uis()
    admin = django_user_model.objects.create_superuser(
        username="uis-click",
        email="uis-click@example.com",
        password="password12",
    )
    StaffVpbxProfile.objects.create(user=admin, extension="", uis_employee_id="55")
    crm_client = Client.objects.create(email="c@example.com", name="C", phone="79161112233")
    seen: dict[str, Any] = {}

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        del timeout
        seen["url"] = req.full_url
        seen["body"] = req.data
        payload = b'{"jsonrpc":"2.0","result":{"data":{"call_session_id":42}}}'
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    client.force_login(admin)
    response = client.post(reverse("admin:crm_client_call_client", args=[crm_client.pk]))
    assert response.status_code == 302
    assert "callapi.uiscom.ru" in seen["url"]
    sent = json.loads(seen["body"].decode())
    assert sent["params"]["employee"] == {"id": 55}
    assert "phone_number" not in sent["params"]["employee"]


@pytest.mark.django_db
def test_uis_click_to_call_wins_over_mango_when_extension_is_uis(
    client: Any,
    django_user_model: Any,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Добавочный 201 — номер UIS: при включённом Mango звонок всё равно идёт в Новосистем."""
    import io
    import urllib.request

    from accounts.models import StaffVpbxProfile
    from crm.models import Client

    settings.MANGO_VPBX_API_KEY = "env-key"
    settings.MANGO_VPBX_API_SALT = "env-salt"
    _enable_uis()
    admin = django_user_model.objects.create_superuser(
        username="uis-ext",
        email="uis-ext@example.com",
        password="password12",
    )
    StaffVpbxProfile.objects.create(user=admin, extension="201", uis_employee_id="55")
    crm_client = Client.objects.create(email="ext@example.com", name="E", phone="79161112233")
    seen: dict[str, Any] = {}

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        del timeout
        seen["url"] = req.full_url
        seen["body"] = req.data
        payload = b'{"jsonrpc":"2.0","result":{"data":{"call_session_id":42}}}'
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    client.force_login(admin)
    response = client.post(reverse("admin:crm_client_call_client", args=[crm_client.pk]))
    assert response.status_code == 302
    assert "callapi.uiscom.ru" in seen["url"]
    assert "mango" not in seen["url"].casefold()
    sent = json.loads(seen["body"].decode())
    assert sent["params"]["employee"] == {"id": 55}


@pytest.mark.django_db
def test_call_client_page_names_the_line_that_will_call(
    client: Any,
    django_user_model: Any,
    settings: Any,
) -> None:
    """Страница подтверждения описывает Новосистем, если звонок пойдёт через UIS."""
    from accounts.models import StaffVpbxProfile
    from crm.models import Client

    _enable_uis(phone="74951234567")
    admin = django_user_model.objects.create_superuser(
        username="uis-copy",
        email="uis-copy@example.com",
        password="password12",
    )
    StaffVpbxProfile.objects.create(user=admin, extension="201", uis_employee_id="55")
    crm_client = Client.objects.create(email="copy@example.com", name="C", phone="79161112233")
    client.force_login(admin)
    html = client.get(reverse("admin:crm_client_call_client", args=[crm_client.pk])).content.decode()
    assert "Новосистем сначала позвонит вам в приложение UIS" in html
    assert "+7 (495) 123-45-67" in html
    assert "Mango сначала позвонит" not in html

    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_enabled = False
    site.mango_enabled = True
    site.save()
    StaffVpbxProfile.objects.filter(user=admin).update(uis_employee_id="")
    off_html = client.get(reverse("admin:crm_client_call_client", args=[crm_client.pk])).content.decode()
    assert "Mango" not in off_html
    assert "включите виджет Новосистем" in off_html


@pytest.mark.django_db
def test_uis_http_error_surfaces_api_message() -> None:
    """Ответ UIS с JSON-ошибкой попадает в текст RuntimeError, а не в общий «недоступен»."""
    import io
    import urllib.error
    import urllib.request

    from crm.novosystem import initiate_employee_call

    _enable_uis()

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        del timeout
        sent = json.loads(req.data.decode())
        assert "phone_number" not in sent["params"]["employee"]
        raise urllib.error.HTTPError(
            req.full_url,
            403,
            "forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":{"message":"ip_not_whitelisted"}}'),
        )

    original = urllib.request.urlopen
    urllib.request.urlopen = _urlopen  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="ip_not_whitelisted"):
            initiate_employee_call(employee_id="55", employee_phone="101", contact="79161112233")
    finally:
        urllib.request.urlopen = original


@pytest.mark.django_db
def test_uis_webhook_url_quotes_secret(client: Any, django_user_model: Any) -> None:
    """Секрет с & и + не разваливает query вебхука на странице интеграций."""
    _enable_uis(secret="a&b+c")
    user = django_user_model.objects.create_superuser(
        username="pbx-secret",
        email="pbx-secret@example.com",
        password="password12",
    )
    client.force_login(user)
    html = client.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    assert "token=a%26b%2Bc" in html
    assert "token=a&b" not in html


@pytest.mark.django_db
def test_uis_webhook_secret_hidden_until_revealed(client: Any, django_user_model: Any) -> None:
    """URL вебхука с секретом был открытым текстом на странице интеграций."""
    _enable_uis(secret="very-secret-token")
    user = django_user_model.objects.create_superuser(
        username="pbx-mask",
        email="pbx-mask@example.com",
        password="password12",
    )
    client.force_login(user)
    html = client.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    summary = html.split('<details class="hoocon-pbx__url">', 1)[1].split("</summary>", 1)[0]
    assert "token=••••" in summary
    assert "very-secret-token" not in summary
    assert "<code>" in html.split('<details class="hoocon-pbx__url">', 1)[1]


@pytest.mark.django_db
def test_novosystem_webhook_non_ascii_token_is_403(client: Any) -> None:
    """compare_digest на не-ASCII токене падал TypeError → 500 вместо 403."""
    _enable_uis()
    body = {"call_session_id": "9100", "direction": "in", "token": "секрет"}
    response = client.post("/api/telephony/novosystem/events/", body, content_type="application/json")
    assert response.status_code == 403


def test_uis_recording_label_is_not_mango() -> None:
    """Запись UIS не подписывается как ещё не скачанная запись Mango."""
    from django.contrib import admin

    from crm.admin import CallAdmin

    labels = CallAdmin(Call, admin.site)
    uis = Call(entry_id="uis:1", recording_id="rec-uis")
    mango = Call(entry_id="mango-1", recording_id="rec-mango")
    assert "личном кабинете Новосистем" in labels.recording_link(uis)
    assert "Mango" not in labels.recording_link(mango)
    assert "ещё не скачана" in labels.recording_link(mango)


def _fake_urlopen(monkeypatch: pytest.MonkeyPatch, *, body: bytes = b"", exc: Exception | None = None) -> None:
    import io
    import urllib.request

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        del req, timeout
        if exc is not None:
            raise exc
        return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)


@pytest.mark.django_db
def test_uis_click_to_call_rejects_incomplete_settings() -> None:
    """Выключенный или недонастроенный виджет UIS не идёт в Call API."""
    from crm.novosystem import initiate_employee_call
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.novosystem_enabled = False
    site.save()
    with pytest.raises(RuntimeError, match="выключен"):
        initiate_employee_call(employee_id="55", employee_phone="", contact="79161112233")

    _enable_uis(token="", phone="")
    with pytest.raises(RuntimeError, match="не настроен"):
        initiate_employee_call(employee_id="55", employee_phone="", contact="79161112233")

    _enable_uis()
    with pytest.raises(RuntimeError, match="ID сотрудника"):
        initiate_employee_call(employee_id="abc", employee_phone="", contact="79161112233")


@pytest.mark.django_db
def test_uis_click_to_call_sends_full_employee_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Полный номер сотрудника уходит в UIS, в отличие от короткого добавочного."""
    import io
    import urllib.request

    from crm.novosystem import initiate_employee_call

    _enable_uis()
    seen: dict[str, Any] = {}

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        del timeout
        seen["body"] = json.loads(req.data.decode())
        return io.BytesIO(b'{"result":{"data":{"call_session_id":"77"}}}')

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    assert initiate_employee_call(employee_id="55", employee_phone="+7 916 000-11-22", contact="79161112233") == 77
    assert seen["body"]["params"]["employee"] == {"id": 55, "phone_number": "79160001122"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("body", "exc", "message"),
    [
        (b"", OSError("timeout"), "недоступен"),
        (b"<html>", None, "не JSON"),
        (b'{"error":{"message":"bad_employee"}}', None, "bad_employee"),
        (b'{"error":"plain_error"}', None, "plain_error"),
        (b'{"result":{"data":{}}}', None, "идентификатор"),
        (b'{"result":{"data":{"call_session_id":true}}}', None, "идентификатор"),
        (b'{"result":{"data":{"call_session_id":"abc"}}}', None, "идентификатор"),
    ],
)
def test_uis_click_to_call_reports_api_failures(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    exc: Exception | None,
    message: str,
) -> None:
    """Сбои Call API UIS превращаются в понятный RuntimeError для менеджера."""
    from crm.novosystem import initiate_employee_call

    _enable_uis()
    _fake_urlopen(monkeypatch, body=body, exc=exc)
    with pytest.raises(RuntimeError, match=message):
        initiate_employee_call(employee_id="55", employee_phone="", contact="79161112233")


@pytest.mark.parametrize("raw", [b"<html>", b'{"error":{}}', b"[]"])
def test_uis_http_error_without_message_falls_back_to_status(raw: bytes) -> None:
    """HTTP-ошибка UIS без JSON-сообщения показывает код статуса."""
    import io
    import urllib.error

    from crm.novosystem import _uis_error_message

    exc = urllib.error.HTTPError("https://x", 502, "bad", hdrs=None, fp=io.BytesIO(raw))  # type: ignore[arg-type]
    assert _uis_error_message(exc) == "HTTP 502"


def test_uis_time_parser_accepts_unix_iso_and_rejects_garbage() -> None:
    """Время UIS: unix (сек/мс), строка цифр, ISO; мусор и пустое — None."""
    from datetime import UTC, datetime

    from crm.novosystem import _parse_uis_time

    expected = datetime(2024, 3, 1, 7, 15, tzinfo=UTC)
    assert _parse_uis_time(1709277300) == expected
    assert _parse_uis_time(1709277300000) == expected
    assert _parse_uis_time("1709277300") == expected
    assert _parse_uis_time("2024-03-01T10:15:00+03:00") == expected
    for empty in (None, "", "   ", True, "not a date", 10**18):
        assert _parse_uis_time(empty) is None


def test_uis_talk_seconds_normalizes_duration() -> None:
    """Длительность UIS: дробь и строка — целые секунды, мусор и минус — 0."""
    from crm.novosystem import _talk_seconds

    assert _talk_seconds("12.7") == 12
    assert _talk_seconds(None) == 0
    assert _talk_seconds("abc") == 0
    assert _talk_seconds(-5) == 0


@pytest.mark.django_db
def test_novosystem_event_updates_open_call_and_logs_once(django_user_model: Any) -> None:
    """Звонок UIS: пустой вебхук игнорируется, открытый звонок дополняется и закрывается."""
    from accounts.models import StaffVpbxProfile
    from crm.models import Activity, ActivityType, Client
    from crm.novosystem import handle_novosystem_event

    _enable_uis()
    manager = django_user_model.objects.create_user(username="uis-ext", email="ext@example.com")
    StaffVpbxProfile.objects.create(user=manager, extension="301")
    crm_client = Client.objects.create(email="uis@example.com", name="UIS", phone="79162223344")

    assert handle_novosystem_event({}) == "ignored"
    first = {"id": "9100", "calling_phone_number": "79162223344", "employee_id": "999"}
    assert handle_novosystem_event(first) == "created"
    call = Call.objects.get(entry_id="uis:9100")
    assert call.state == "appeared"
    assert call.manager_id is None

    final = {
        **first,
        "extension": "301",
        "start_time": "2024-03-01T10:00:00+03:00",
        "finish_time": "2024-03-01T10:05:00+03:00",
        "talk_time_duration": 90,
        "call_records": ["rec-1"],
    }
    assert handle_novosystem_event(final) == "updated"
    call.refresh_from_db()
    assert call.state == "disconnected"
    assert call.manager_id == manager.pk
    assert call.recording_id == "rec-1"
    assert call.talk_duration == 90
    assert call.finished_at is not None
    assert Activity.objects.filter(client=crm_client, activity_type=ActivityType.CALL).count() == 1


@pytest.mark.django_db
def test_staff_telephony_permission_names_drop_retired_label() -> None:
    """Старое имя права оставалось в списке прав пользователя после смены подписи."""
    import importlib

    from django.apps import apps
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from accounts.models import StaffVpbxProfile

    rename = importlib.import_module(
        "accounts.migrations.0019_rename_staff_telephony_permissions"
    ).rename_staff_telephony_permissions

    content_type = ContentType.objects.get_for_model(StaffVpbxProfile)
    perm = Permission.objects.get(content_type=content_type, codename="view_staffvpbxprofile")
    perm.name = "Can view Добавочный сотрудника (Mango)"
    perm.save(update_fields=["name"])
    rename(apps, None)
    perm.refresh_from_db()
    assert perm.name == "Can view Телефония сотрудника"
    assert "Mango" not in perm.name


@pytest.mark.django_db
def test_admin_telephony_widget_ignores_retired_provider(client: Any, django_user_model: Any) -> None:
    """Админка не сохраняет снятый виджет: ни file://, ни обычный https-шаблон."""
    from sitesettings.models import SiteSettings

    user = django_user_model.objects.create_superuser(
        username="pbx-scheme",
        email="pbx-scheme@example.com",
        password="password12",
    )
    client.force_login(user)
    site = SiteSettings.load()
    site.mango_enabled = False
    site.mango_callback_webhook_url = "https://kept.example/hook"
    site.save()
    url = reverse("admin:sitesettings_telephony_widget")
    client.post(url, {"provider": "mango", "mango_callback_webhook_url": "file:///etc/passwd", "mango_enabled": "on"})
    site.refresh_from_db()
    assert site.mango_callback_webhook_url == "https://kept.example/hook"
    assert site.mango_enabled is False

    ok = "https://integration-webhook.example.test/hook?EmployeeNUM={ext}&TelNumbr={num}"
    client.post(url, {"provider": "mango", "mango_callback_webhook_url": ok, "mango_enabled": "on"})
    site.refresh_from_db()
    assert site.mango_callback_webhook_url == "https://kept.example/hook"
    assert site.mango_enabled is False


@pytest.mark.django_db
def test_settings_save_keeps_round_robin_cursor(django_user_model: Any) -> None:
    """site.save() из формы телефонии затирал курсор round-robin, сдвинутый роутером."""
    from sitesettings.models import SiteSettings

    picked = django_user_model.objects.create_user(username="rr-picked", password="x", is_staff=True)
    stale = SiteSettings.load()
    fresh = SiteSettings.load()
    fresh.lead_rr_last_user = picked
    fresh.save(update_fields=["lead_rr_last_user", "updated_at"])

    stale.mango_enabled = True
    stale.save()
    row = SiteSettings.load()
    assert row.mango_enabled is True
    assert row.lead_rr_last_user_id == picked.pk


@pytest.mark.django_db
def test_unknown_finished_call_opens_one_card_and_reuses_it(django_user_model: Any) -> None:
    """Незнакомый номер после разговора — одна карточка менеджера, повтор не плодит вторую и не шлёт письмо."""
    from unittest.mock import patch

    from accounts.models import StaffVpbxProfile
    from crm.models import Client
    from crm.novosystem import handle_novosystem_event
    from leads.models import Lead

    _enable_uis()
    manager = django_user_model.objects.create_user(
        username="caller",
        email="caller@hoocon.test",
        is_staff=True,
    )
    StaffVpbxProfile.objects.create(user=manager, uis_employee_id="55", extension="201")

    def event(session: str) -> dict[str, str]:
        return {
            "id": session,
            "direction": "in",
            "contact_phone_number": "79001112233",
            "employee_id": "55",
            "finish_time": "2024-03-01T10:05:00+03:00",
        }

    with (
        patch("leads.tasks.send_lead_notification.delay") as staff_mail,
        patch("leads.tasks.send_lead_client_confirmation.delay") as client_mail,
    ):
        assert handle_novosystem_event(event("1")) == "created"
        assert handle_novosystem_event(event("2")) == "created"
        staff_mail.assert_not_called()
        client_mail.assert_not_called()

    stub = Client.objects.get(email="79001112233@call.invalid")
    assert stub.assignee_id == manager.pk
    assert Lead.objects.filter(client=stub).count() == 1
    assert Lead.objects.get(client=stub).assignee_id == manager.pk
    assert Call.objects.filter(client=stub).count() == 2


@pytest.mark.django_db
def test_ringing_call_and_company_number_do_not_open_a_card() -> None:
    """Пока трубку не положили и на номер компании карточку не заводим."""
    from crm.models import Client
    from crm.novosystem import handle_novosystem_event

    _enable_uis(phone="74951234567")
    assert handle_novosystem_event({"id": "ring", "contact_phone_number": "79002223344"}) == "created"
    assert Client.objects.count() == 0
    assert (
        handle_novosystem_event(
            {
                "id": "office",
                "contact_phone_number": "74951234567",
                "finish_time": "2024-03-01T10:05:00+03:00",
            },
        )
        == "created"
    )
    assert Client.objects.count() == 0


@pytest.mark.django_db
def test_real_card_wins_over_call_stub_and_click_to_call_binds_session(django_user_model: Any) -> None:
    """Живая карточка важнее заглушки; звонок из карточки садится на неё, даже если UIS прислал другой номер."""
    from accounts.models import StaffVpbxProfile
    from crm.call_cards import remember_uis_session
    from crm.models import Client
    from crm.novosystem import handle_novosystem_event

    _enable_uis()
    manager = django_user_model.objects.create_user(username="bind", email="bind@hoocon.test", is_staff=True)
    StaffVpbxProfile.objects.create(user=manager, uis_employee_id="77")
    Client.objects.create(email="79003334455@call.invalid", name="Звонок", phone="79003334455")
    real = Client.objects.create(email="real@acme.test", name="Реальный", phone="79003334455")

    handle_novosystem_event(
        {
            "id": "match",
            "contact_phone_number": "79003334455",
            "finish_time": "2024-03-01T10:05:00+03:00",
            "employee_id": "77",
        },
    )
    assert Call.objects.get(entry_id="uis:match").client_id == real.pk

    opened = Client.objects.create(email="opened@acme.test", name="Из карточки", phone="79004445566")
    remember_uis_session(4242, client_id=opened.pk, manager_id=manager.pk)
    handle_novosystem_event(
        {
            "id": "4242",
            "direction": "out",
            "contact_phone_number": "79005556677",
            "finish_time": "2024-03-01T11:00:00+03:00",
            "employee_id": "77",
        },
    )
    bound = Call.objects.get(entry_id="uis:4242")
    assert bound.client_id == opened.pk
    assert not Client.objects.filter(email="79005556677@call.invalid").exists()
