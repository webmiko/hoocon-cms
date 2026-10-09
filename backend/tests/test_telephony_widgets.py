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
    """Страница интеграций содержит формы Mango и Новосистем."""
    from sitesettings.models import SiteSettings

    SiteSettings.load()
    user = django_user_model.objects.create_superuser(
        username="pbx-page",
        email="pbx-page@example.com",
        password="password12",
    )
    client.force_login(user)
    html = client.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    assert 'id="telephony-mango"' in html
    assert 'id="telephony-novosystem"' in html
    assert html.count("hoocon-pbx__widget hoocon-integrations__card") == 2
    assert '<form class="hoocon-pbx__widget' not in html
    assert html.count('hoocon-pbx__state--on">Виджет включён') == 2
    assert html.count('hoocon-pbx__state--off">Виджет выключен') == 2
    assert html.count('hoocon-pbx__state--partial">Не полностью') == 2
    assert html.count('type="checkbox" class="hoocon-toggle"') == 2
    assert "/api/telephony/novosystem/events/" in html
    assert "hoocon-pbx__save" in html


def test_telephony_save_buttons_pinned_to_card_bottom() -> None:
    """Кнопки «Сохранить» Mango и Новосистем стоят на одной линии внизу карточек."""
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8"
    )

    def rule(selector: str) -> str:
        match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", css)
        assert match, selector
        return match.group(1)

    assert "align-items: stretch" in rule(".hoocon-pbx")
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
    assert "Mango" in labels.recording_link(mango)


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
def test_mango_widget_rejects_non_https_callback(client: Any, django_user_model: Any) -> None:
    """Форма виджета сохраняла file:// и http://внутренний-хост как URL вебхука."""
    from sitesettings.models import SiteSettings

    user = django_user_model.objects.create_superuser(
        username="pbx-scheme",
        email="pbx-scheme@example.com",
        password="password12",
    )
    client.force_login(user)
    url = reverse("admin:sitesettings_telephony_widget")
    client.post(url, {"provider": "mango", "mango_callback_webhook_url": "file:///etc/passwd"})
    assert SiteSettings.load().mango_callback_webhook_url == ""

    ok = "https://integration-webhook.mango-office.ru/webhookapp/common?EmployeeNUM={ext}&TelNumbr={num}"
    client.post(url, {"provider": "mango", "mango_callback_webhook_url": ok})
    assert SiteSettings.load().mango_callback_webhook_url == ok


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
