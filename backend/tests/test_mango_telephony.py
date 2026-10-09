"""Tests for Mango VPBX integration: webhook signature, events, dedup.

Сценарии: невалидная подпись → 403; call-события создают/обновляют Call,
резолвят клиента по цифрам телефона и менеджера по добавочному; повторные
и устаревшие seq не дублируют; Disconnected пишет Activity один раз;
recording-событие ставит задачу на скачивание; callback-команда подписана.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from crm.models import Activity, ActivityType, Call, CallState, Client


def _mango_payload(**over: Any) -> dict[str, Any]:
    """Mango call-event shape (входящий: клиент → добавочный менеджера)."""
    payload: dict[str, Any] = {
        "entry_id": "entry-1",
        "call_id": "call-1",
        "timestamp": 1760000000,
        "seq": 1,
        "call_state": "Appeared",
        "location": "abonent",
        "from": {"number": "79151112233"},
        "to": {"extension": "101"},
    }
    payload.update(over)
    return payload


def _signed_body(
    payload: dict[str, Any],
    *,
    key: str = "test-key",
    salt: str = "test-salt",
    bad_sign: bool = False,
) -> dict[str, str]:
    """Form body as Mango sends it: vpbx_api_key + json + sign."""
    raw = json.dumps(payload, ensure_ascii=False)
    sign = hashlib.sha256(f"{key}{raw}{salt}".encode()).hexdigest()
    return {
        "vpbx_api_key": key,
        "json": raw,
        "sign": "00" * 32 if bad_sign else sign,
    }


@pytest.fixture()
def mango_settings(settings: Any) -> Any:
    settings.MANGO_VPBX_API_KEY = "test-key"
    settings.MANGO_VPBX_API_SALT = "test-salt"
    return settings


URL = "/api/telephony/mango/events/"


@pytest.mark.django_db
def test_webhook_rejects_bad_signature(client: Any, mango_settings: Any) -> None:
    """403 when sign does not match sha256(key + json + salt)."""
    resp = client.post(URL, _signed_body(_mango_payload(), bad_sign=True))
    assert resp.status_code == 403
    assert Call.objects.count() == 0


@pytest.mark.django_db
def test_webhook_non_ascii_sign_is_403_not_500(client: Any, mango_settings: Any) -> None:
    """compare_digest on non-ASCII str raised TypeError → 500 for a forged sign/key."""
    body = _signed_body(_mango_payload())
    assert client.post(URL, {**body, "sign": "подпись"}).status_code == 403
    assert client.post(URL, {**body, "vpbx_api_key": "ключ"}).status_code == 403
    assert Call.objects.count() == 0


@pytest.mark.django_db
def test_webhook_rejects_when_not_configured(client: Any, settings: Any) -> None:
    """403 when MANGO keys are empty — webhook is closed by default."""
    settings.MANGO_VPBX_API_KEY = ""
    settings.MANGO_VPBX_API_SALT = ""
    resp = client.post(URL, _signed_body(_mango_payload()))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_call_event_creates_call_resolves_client_and_manager(
    client: Any,
    mango_settings: Any,
) -> None:
    """Inbound call → Call row + client by phone digits + manager by ext."""
    from django.contrib.auth import get_user_model

    from accounts.models import StaffVpbxProfile

    crm_client = Client.objects.create(
        email="buyer@example.test",
        name="B",
        phone="+7 (915) 111-22-33",
    )
    manager = get_user_model().objects.create_user(
        username="m101",
        email="m101@example.com",
        password="password12",
        is_staff=True,
    )
    StaffVpbxProfile.objects.create(user=manager, extension="101")

    resp = client.post(URL, _signed_body(_mango_payload(seq=1)))
    assert resp.status_code == 200

    call = Call.objects.get(entry_id="entry-1")
    assert call.direction == "inbound"
    assert call.state == CallState.APPEARED
    assert call.client_id == crm_client.pk
    assert call.manager_id == manager.pk
    assert call.extension == "101"


@pytest.mark.django_db
def test_call_flow_connected_then_disconnected_creates_activity(
    client: Any,
    mango_settings: Any,
) -> None:
    """Appeared → Connected → Disconnected: Activity only on first finish."""
    crm_client = Client.objects.create(
        email="buyer@example.test",
        name="B",
        phone="79151112233",
    )

    client.post(URL, _signed_body(_mango_payload(seq=1, timestamp=100)))
    client.post(
        URL,
        _signed_body(_mango_payload(seq=2, call_state="Connected", timestamp=105)),
    )
    resp = client.post(
        URL,
        _signed_body(_mango_payload(seq=3, call_state="Disconnected", timestamp=170)),
    )
    assert resp.status_code == 200

    call = Call.objects.get(entry_id="entry-1")
    assert call.state == CallState.DISCONNECTED
    assert call.talk_duration == 65

    act = Activity.objects.get(client=crm_client)
    assert act.activity_type == ActivityType.CALL
    assert "Входящий" in act.subject
    assert "1:05" in act.body


@pytest.mark.django_db
def test_repeat_disconnect_does_not_duplicate_activity(
    client: Any,
    mango_settings: Any,
) -> None:
    """Mango retries Disconnected → no second Activity row."""
    Client.objects.create(email="b@example.test", name="B", phone="79151112233")
    for seq, state, ts in (
        (1, "Appeared", 100),
        (2, "Connected", 105),
        (3, "Disconnected", 170),
        (3, "Disconnected", 170),
    ):
        client.post(URL, _signed_body(_mango_payload(seq=seq, call_state=state, timestamp=ts)))
    assert Activity.objects.filter(activity_type=ActivityType.CALL).count() == 1


@pytest.mark.django_db
def test_out_of_order_seq_ignored(client: Any, mango_settings: Any) -> None:
    """Older seq after newer one does not roll the state back."""
    client.post(
        URL,
        _signed_body(_mango_payload(seq=5, call_state="Disconnected", timestamp=200)),
    )
    resp = client.post(
        URL,
        _signed_body(_mango_payload(seq=3, call_state="Connected", timestamp=150)),
    )
    assert resp.status_code == 200
    call = Call.objects.get(entry_id="entry-1")
    assert call.state == CallState.DISCONNECTED


@pytest.mark.django_db
def test_outbound_direction(client: Any, mango_settings: Any) -> None:
    """from.extension + to.number → outbound; client resolves by to_number."""
    crm_client = Client.objects.create(
        email="b@example.test",
        name="B",
        phone="79151112233",
    )
    payload = _mango_payload(
        seq=1,
        **{
            "from": {"extension": "101"},
            "to": {"number": "79151112233"},
        },
    )
    resp = client.post(URL, _signed_body(payload))
    assert resp.status_code == 200
    call = Call.objects.get(entry_id="entry-1")
    assert call.direction == "outbound"
    assert call.client_id == crm_client.pk


@pytest.mark.django_db
def test_unknown_caller_stored_without_client(client: Any, mango_settings: Any) -> None:
    """Unknown number → Call kept (switchboard), no client/Activity."""
    resp = client.post(URL, _signed_body(_mango_payload(seq=1)))
    assert resp.status_code == 200
    call = Call.objects.get(entry_id="entry-1")
    assert call.client_id is None
    assert Activity.objects.count() == 0


@pytest.mark.django_db
def test_recording_event_links_and_enqueues(
    client: Any,
    mango_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """recording Completed → recording_id saved + fetch task enqueued."""
    client.post(URL, _signed_body(_mango_payload(seq=1)))
    calls: list[str] = []

    class _Task:
        @staticmethod
        def delay(entry_id: str) -> None:
            calls.append(entry_id)

    monkeypatch.setattr("crm.tasks.fetch_mango_recording", _Task)

    resp = client.post(
        URL,
        _signed_body(
            {
                "entry_id": "entry-1",
                "recording_id": "rec-1",
                "recording_state": "Completed",
                "seq": 9,
                "extension": "101",
            }
        ),
    )
    assert resp.status_code == 200
    call = Call.objects.get(entry_id="entry-1")
    assert call.recording_id == "rec-1"
    assert calls == ["entry-1"]


@pytest.mark.django_db
def test_mango_command_signature(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """initiate_callback sends signed form; sign matches api docs scheme."""
    settings.MANGO_VPBX_API_KEY = "test-key"
    settings.MANGO_VPBX_API_SALT = "test-salt"

    captured: dict[str, Any] = {}

    class _Resp:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"result": 1000, "call_id": "x"}'

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        body = req.data.decode()
        for pair in body.split("&"):
            k, v = pair.split("=", 1)
            captured[k] = v
        captured["url"] = req.full_url
        return _Resp()

    import urllib.parse

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    from crm.mango import initiate_callback

    result = initiate_callback("101", "79151112233")
    assert result["result"] == 1000
    assert captured["url"].endswith("/vpbx/commands/callback")
    assert captured["vpbx_api_key"] == "test-key"
    sent_json = urllib.parse.unquote_plus(captured["json"])
    expected = hashlib.sha256(f"test-key{sent_json}test-salt".encode()).hexdigest()
    assert captured["sign"] == expected
    payload = json.loads(sent_json)
    assert payload["from"] == {"extension": "101"}
    assert payload["to_number"] == "79151112233"


@pytest.mark.django_db
def test_webhook_bad_json_returns_400(client: Any, mango_settings: Any) -> None:
    """Подпись верная, но json не парсится → 400, событие не обрабатывается."""
    raw = "not-json"
    sign = hashlib.sha256(f"test-key{raw}test-salt".encode()).hexdigest()
    resp = client.post(URL, {"vpbx_api_key": "test-key", "json": raw, "sign": sign})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_fetch_recording_task_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Celery-таска: нет звонка / нет recording_id / успех / пусто / retry."""
    from crm import tasks as crm_tasks

    assert crm_tasks.fetch_mango_recording("missing-entry") == "no-call"

    call = Call.objects.create(entry_id="e-norec")
    assert crm_tasks.fetch_mango_recording("e-norec") == "no-recording-id"

    call.recording_id = "rec-1"
    call.save(update_fields=["recording_id"])

    saved: list[str] = []

    def _fake_storage_save(name: str, content: Any, max_length: Any = None) -> str:
        saved.append(name)
        return name

    storage = Call._meta.get_field("recording").storage  # noqa: SLF001
    monkeypatch.setattr(storage, "save", _fake_storage_save)
    monkeypatch.setattr("crm.mango.download_recording", lambda rid: b"MP3")
    assert crm_tasks.fetch_mango_recording("e-norec") == "saved"
    assert len(saved) == 1
    assert saved[0].startswith("call_recordings/e-norec_")
    assert saved[0].endswith(".mp3")

    monkeypatch.setattr("crm.mango.download_recording", lambda rid: b"")
    Call.objects.create(entry_id="e-empty", recording_id="rec-2")
    assert crm_tasks.fetch_mango_recording("e-empty") == "empty"

    def _boom(rid: str) -> bytes:
        raise RuntimeError("mango down")

    monkeypatch.setattr("crm.mango.download_recording", _boom)
    call3 = Call.objects.create(entry_id="e-err", recording_id="rec-3")
    with pytest.raises(RuntimeError, match="mango down"):
        crm_tasks.fetch_mango_recording("e-err")

    call3.recording = "call_recordings/x.mp3"
    call3.save(update_fields=["recording"])
    assert crm_tasks.fetch_mango_recording("e-err") == "already"


def test_download_recording_binary_and_empty(
    monkeypatch: pytest.MonkeyPatch,
    mango_settings: Any,
) -> None:
    """download_recording отдаёт байты из raw; JSON без raw → None."""
    from crm import mango

    paths: list[str] = []

    def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        paths.append(path)
        return {"raw": b"BIN"}

    monkeypatch.setattr(mango, "_mango_post", _post)
    assert mango.download_recording("rec-1") == b"BIN"
    assert paths == ["queries/recording/post"]
    monkeypatch.setattr(mango, "_mango_post", lambda path, payload: {"result": 0})
    assert mango.download_recording("rec-1") is None


@pytest.mark.django_db
def test_second_disconnect_same_timestamp_logs_once(client: Any, mango_settings: Any) -> None:
    """M18: второй Disconnected (другое плечо, тот же ts) не дублирует «Звонок» в ленте."""
    card = Client.objects.create(name="К", email="dup-call@acme.test", phone="+7 915 111-22-33")
    for seq, state in ((1, "Appeared"), (2, "Connected"), (3, "Disconnected"), (4, "Disconnected")):
        payload = _mango_payload(seq=seq, call_state=state, call_id=f"leg-{seq}")
        assert client.post(URL, _signed_body(payload)).status_code == 200
    assert Activity.objects.filter(client=card, subject__icontains="звонок").count() == 1


@pytest.mark.django_db
def test_finished_call_state_not_rolled_back(client: Any, mango_settings: Any) -> None:
    """M18: после Disconnected позднее событие другого плеча не откатывает state."""
    for seq, state in ((1, "Appeared"), (2, "Disconnected"), (3, "Connected")):
        payload = _mango_payload(seq=seq, call_state=state, timestamp=1760000000 + seq)
        client.post(URL, _signed_body(payload))
    call = Call.objects.get(entry_id="entry-1")
    assert call.state == CallState.DISCONNECTED
    assert call.finished_at is not None


@pytest.mark.django_db
def test_call_skips_inactive_merged_card(client: Any, mango_settings: Any) -> None:
    """M19: звонок не падает на деактивированный дубль с тем же номером."""
    merged = Client.objects.create(name="Дубль", email="old@acme.test", phone="+79151112233", is_active=False)
    live = Client.objects.create(name="Живая", email="new@acme.test", phone="+79151112233")
    assert merged.pk < live.pk
    client.post(URL, _signed_body(_mango_payload()))
    assert Call.objects.get(entry_id="entry-1").client_id == live.pk


@pytest.mark.django_db
def test_merge_clients_moves_calls() -> None:
    """M19: объединение карточек переносит и звонки («все связи»)."""
    from crm.services import merge_clients

    target = Client.objects.create(name="Цель", email="target@acme.test")
    dup = Client.objects.create(name="Дубль", email="dup@acme.test")
    call = Call.objects.create(client=dup, entry_id="merge-1", direction="inbound")
    moved = merge_clients(target, [dup])
    call.refresh_from_db()
    assert call.client_id == target.pk
    assert moved["calls"] == 1


@pytest.mark.django_db
def test_recording_download_uses_queries_endpoint(monkeypatch: pytest.MonkeyPatch, mango_settings: Any) -> None:
    """M16: запись качается через /vpbx/queries/recording/post (не commands/)."""
    captured: dict[str, str] = {}

    class _Resp:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return b"ID3-mp3-bytes"

    def _urlopen(req: Any, timeout: int = 0) -> Any:
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    from crm.mango import download_recording

    assert download_recording("rec-9") == b"ID3-mp3-bytes"
    assert captured["url"] == "https://app.mango-office.ru/vpbx/queries/recording/post"


@pytest.mark.django_db
@pytest.mark.parametrize("suffix", ["call", "summary", "recording", "record/added", "call/"])
def test_webhook_accepts_mango_event_paths(client: Any, mango_settings: Any, suffix: str) -> None:
    """M16: Mango шлёт на <base>/events/call|summary|recording — без слеша на конце."""
    raw = json.dumps({"entry_id": "path-1", "call_state": "Appeared", "seq": 1, "timestamp": 1700000000})
    sign = hashlib.sha256(f"test-key{raw}test-salt".encode()).hexdigest()
    resp = client.post(f"{URL}{suffix}", {"vpbx_api_key": "test-key", "json": raw, "sign": sign})
    assert resp.status_code == 200, suffix


@pytest.mark.django_db
def test_callback_non_success_result_raises(monkeypatch: pytest.MonkeyPatch, mango_settings: Any) -> None:
    """M17: HTTP 200 с result≠1000 — ошибка, а не «звонок пошёл»."""
    from crm import mango

    monkeypatch.setattr(mango, "mango_command", lambda cmd, payload: {"result": 3102})
    with pytest.raises(RuntimeError, match="3102"):
        mango.initiate_callback("101", "79151112233")


@pytest.mark.django_db
def test_mango_command_requires_keys(settings: Any) -> None:
    """Без key/salt — RuntimeError до сети."""
    from crm import mango

    settings.MANGO_VPBX_API_KEY = ""
    settings.MANGO_VPBX_API_SALT = ""
    assert mango.mango_configured() is False
    with pytest.raises(RuntimeError):
        mango.mango_command("callback", {})


@pytest.mark.django_db
def test_mango_command_transport_error(
    monkeypatch: pytest.MonkeyPatch,
    mango_settings: Any,
) -> None:
    """OSError на транспорте → RuntimeError для retry/сообщения менеджеру."""
    import urllib.request

    from crm import mango

    def _down(req: Any, timeout: int = 0) -> Any:
        raise OSError("conn refused")

    monkeypatch.setattr(urllib.request, "urlopen", _down)
    with pytest.raises(RuntimeError, match="недоступен"):
        mango.initiate_callback("101", "79151112233")


@pytest.mark.django_db
def test_callback_webhook_substitutes_digits(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """«Вебхуки»-канал: {ext}/{num} подставляются цифрами, GET на Mango."""
    import urllib.request

    from crm import mango

    settings.MANGO_CALLBACK_WEBHOOK_URL = (
        "https://integration-webhook.mango-office.ru/webhookapp/common"
        "?code=x&API_key=y&Action=Callback&EmployeeNUM={ext}&TelNumbr={num}"
    )
    hits: list[str] = []

    class _Resp:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return b""

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda url, timeout=0: hits.append(url) or _Resp(),
    )
    mango.initiate_callback_webhook("101", "+7 (915) 111-22-33")
    assert "EmployeeNUM=101" in hits[0]
    assert "TelNumbr=79151112233" in hits[0]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "template",
    ["file:///etc/passwd?{ext}{num}", "http://10.0.0.5/hook?{ext}{num}", "ftp://x/{ext}{num}", "https:///{ext}"],
)
def test_callback_webhook_rejects_non_https(settings: Any, monkeypatch: pytest.MonkeyPatch, template: str) -> None:
    """URL вебхука без проверки схемы: urlopen читал file:// и ходил во внутреннюю сеть."""
    import urllib.request

    from crm import mango

    settings.MANGO_CALLBACK_WEBHOOK_URL = template
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("urlopen must not run"))
    with pytest.raises(RuntimeError, match="https://"):
        mango.initiate_callback_webhook("101", "79151112233")


@pytest.mark.django_db
def test_callback_webhook_unconfigured(settings: Any) -> None:
    """Без MANGO_CALLBACK_WEBHOOK_URL — понятный RuntimeError."""
    from crm import mango

    settings.MANGO_CALLBACK_WEBHOOK_URL = ""
    assert mango.webhook_callback_configured() is False
    with pytest.raises(RuntimeError):
        mango.initiate_callback_webhook("101", "79151112233")


@pytest.mark.django_db
def test_client_change_page_has_call_button(
    client: Any,
    django_user_model: Any,
) -> None:
    """Кнопка «Позвонить» — стилизованный object-tools item, не голый <a>."""
    from django.urls import reverse

    admin = django_user_model.objects.create_superuser(
        username="admin-call",
        email="admin-call@example.test",
        password="password12",
    )
    crm_client = Client.objects.create(email="b@example.test", name="B", phone="79151112233")
    client.force_login(admin)
    resp = client.get(reverse("admin:crm_client_change", args=[crm_client.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert f"/admin/crm/client/{crm_client.pk}/call-client/" in html
    # Unfold-кнопка: bordered li + icon, иначе это незаметный текст-линк.
    assert 'material-symbols-outlined">call' in html
    assert "hover:bg-base-500/8" in html


@pytest.mark.django_db
def test_client_change_page_inline_quick_actions(
    client: Any,
    django_user_model: Any,
) -> None:
    """Инлайн-кнопки «Написать»/«Позвонить» у полей email/phone подключены на change-странице."""
    from django.contrib.staticfiles import finders
    from django.urls import reverse

    admin = django_user_model.objects.create_superuser(
        username="admin-qa",
        email="admin-qa@example.test",
        password="password12",
    )
    crm_client = Client.objects.create(email="b@example.test", name="B", phone="79151112233")
    client.force_login(admin)
    resp = client.get(reverse("admin:crm_client_change", args=[crm_client.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "hoocon-client-quick-actions.js" in html
    assert 'id="id_email"' in html
    assert 'id="id_phone"' in html

    # Скрипт активируется только на /change/ и ведёт на существующие Admin-views.
    path = finders.find("admin/js/hoocon-client-quick-actions.js")
    assert path is not None
    source = open(path).read()
    assert "/change/" in source
    assert "/compose-email/" in source
    assert "/call-client/" in source
    assert "id_email" in source
    assert "id_phone" in source


@pytest.mark.django_db
def test_call_client_view_blockers_without_mango(
    client: Any,
    django_user_model: Any,
    settings: Any,
) -> None:
    """Без ключей и webhook-URL страница показывает блокер, не 500."""
    from django.urls import reverse

    settings.MANGO_VPBX_API_KEY = ""
    settings.MANGO_VPBX_API_SALT = ""
    settings.MANGO_CALLBACK_WEBHOOK_URL = ""
    admin = django_user_model.objects.create_superuser(
        username="admin-call2",
        email="admin-call2@example.test",
        password="password12",
    )
    crm_client = Client.objects.create(email="b@example.test", name="B", phone="79151112233")
    client.force_login(admin)
    resp = client.get(reverse("admin:crm_client_call_client", args=[crm_client.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Mango" in html
    # Unfold-разметка: карточка/кнопки, а не голый stock-админский submit-row.
    assert "rounded-default" in html
    assert "submit-row" not in html


@pytest.mark.django_db
def test_telephony_helper_edge_cases() -> None:
    """Мелкие ветки парсинга: мусорный ts/endpoint, короткий номер, пустой ext."""
    from crm.telephony import (
        _client_and_extension,
        _epoch,
        _resolve_client,
        _resolve_manager,
        handle_mango_event,
    )

    assert _epoch("junk") is None
    assert _epoch(None) is None
    assert _epoch(0) is not None

    # Оба endpoint'а с extension → неоднозначный, берём from-номер.
    num, ext = _client_and_extension({"from": {"extension": "1"}, "to": {"extension": "2"}})
    assert (num, ext) == ("", "2")
    num, ext = _client_and_extension({"from": "junk", "to": "junk"})
    assert (num, ext) == ("", "")

    assert _resolve_client("123") is None
    assert _resolve_manager("") is None

    assert handle_mango_event("junk") == "skipped"
    assert handle_mango_event({}) == "ignored"
    assert handle_mango_event({"call_state": "Appeared"}) == "skipped"


def test_normalize_phone_digits() -> None:
    from crm.telephony import normalize_phone_digits

    assert normalize_phone_digits("+7 (915) 111-22-33") == "79151112233"
    assert normalize_phone_digits("8 915 111 2233") == "79151112233"
    assert normalize_phone_digits("9151112233") == "79151112233"
    assert normalize_phone_digits("101") == "101"
    assert normalize_phone_digits("") == ""
