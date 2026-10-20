"""Browser softphone (UIS WebRTC): token privacy, access rules, CSP scope, wiring.

Ожидания — из замысла: токен личный (чужому не отдаётся, в HTML не попадает,
в базе зашифрован), карточка клиента по номеру — только в пределах прав
менеджера, UIS-хосты в CSP — только у окна телефона.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.test import Client as HttpClient
from django.test import RequestFactory
from django.urls import reverse

from accounts.forms import StaffVpbxProfileForm
from accounts.models import StaffVpbxProfile
from config.csp_middleware import SOFTPHONE_PATH
from config.unfold_callbacks import _versioned_static, admin_softphone_js
from crm.models import Client
from crm.softphone import UIS_WEBRTC_LIB
from sitesettings.models import SiteSettings

STATIC_JS = Path(__file__).resolve().parents[1] / "static/admin/js"


def _code_only(source: str) -> str:
    """JS without comments, so a lint matches code and not prose."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"//[^\n]*", "", without_blocks)


def _widget(*, enabled: bool = True) -> None:
    site = SiteSettings.load()
    site.novosystem_enabled = enabled
    site.save()


def _staff(
    django_user_model: Any,
    name: str,
    *,
    token: str = "",
    profile_enabled: bool = True,
    is_staff: bool = True,
    perms: tuple[str, ...] = (),
) -> Any:
    user = django_user_model.objects.create_user(
        username=name,
        email=f"{name}@example.test",
        password="password12",
        is_staff=is_staff,
        first_name=name.title(),
    )
    if token or not profile_enabled:
        StaffVpbxProfile.objects.create(user=user, uis_webrtc_token=token, is_enabled=profile_enabled)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _csrf_client(user: Any) -> HttpClient:
    """Client that really enforces CSRF, logged in as ``user``."""
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(user)
    return http


def _csp(response: Any) -> str:
    headers = response.headers
    return headers.get("Content-Security-Policy") or headers.get("Content-Security-Policy-Report-Only")


def _directive(csp: str, name: str) -> str:
    return next(part.strip() for part in csp.split(";") if part.strip().startswith(name))


# ── Хранение токена ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_webrtc_token_is_encrypted_at_rest(django_user_model: Any) -> None:
    """Дамп базы не раскрывает токен: в колонке Fernet, читает его только свойство профиля."""
    user = _staff(django_user_model, "agent", token="plain-webrtc-token-123")
    raw = StaffVpbxProfile.objects.values_list("uis_webrtc_token", flat=True).get(user=user)
    assert raw.startswith("fernet1:")
    assert "plain-webrtc-token-123" not in raw

    profile = StaffVpbxProfile.objects.get(user=user)
    assert profile.uis_webrtc_token_plain == "plain-webrtc-token-123"
    profile.save()  # повторное сохранение не шифрует шифртекст ещё раз
    assert StaffVpbxProfile.objects.get(user=user).uis_webrtc_token_plain == "plain-webrtc-token-123"


# ── Выдача токена: только свой ──────────────────────────────────────────────


def _post_session(user: Any) -> Any:
    """POST the token endpoint like the window does: real CSRF cookie + header."""
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(user)
    http.get(reverse("crm_softphone_window"))  # Django sets the csrftoken cookie here
    return http.post(reverse("crm_softphone_session"), HTTP_X_CSRFTOKEN=http.cookies["csrftoken"].value)


@pytest.mark.django_db
def test_session_returns_only_own_token(django_user_model: Any) -> None:
    """Каждый сотрудник получает свой токен и ни байта чужого."""
    _widget()
    alice = _staff(django_user_model, "alice", token="token-of-alice")
    bob = _staff(django_user_model, "bob", token="token-of-bob")

    resp_alice = _post_session(alice)
    resp_bob = _post_session(bob)

    assert resp_alice.status_code == 200
    assert resp_alice.json()["token"] == "token-of-alice"
    assert b"token-of-bob" not in resp_alice.content
    assert resp_bob.status_code == 200
    assert resp_bob.json()["token"] == "token-of-bob"
    assert b"token-of-alice" not in resp_bob.content


@pytest.mark.django_db
def test_session_is_not_cacheable_and_post_only(client: Any, django_user_model: Any) -> None:
    """Токен не кэшируется браузером/прокси; GET по адресу токена — 405."""
    _widget()
    user = _staff(django_user_model, "agent", token="tok")
    client.force_login(user)
    url = reverse("crm_softphone_session")

    assert client.get(url).status_code == 405
    response = client.post(url)
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.django_db
def test_session_requires_csrf(django_user_model: Any) -> None:
    """Чужая страница не может заставить браузер менеджера отдать токен (CSRF)."""
    _widget()
    user = _staff(django_user_model, "agent", token="secret-token")
    response = _csrf_client(user).post(reverse("crm_softphone_session"))
    assert response.status_code == 403
    assert b"secret-token" not in response.content


@pytest.mark.django_db
def test_session_refuses_anonymous(client: Any, django_user_model: Any) -> None:
    """Без входа токен не выдаётся даже при верном адресе."""
    _widget()
    _staff(django_user_model, "agent", token="secret-token")
    response = client.post(reverse("crm_softphone_session"))
    assert response.status_code == 403
    assert b"secret-token" not in response.content


@pytest.mark.django_db
def test_session_refuses_non_staff_even_with_token(client: Any, django_user_model: Any) -> None:
    """Аккаунт без is_staff токен не получит, даже если профиль с токеном есть."""
    _widget()
    user = _staff(django_user_model, "outsider", token="secret-token", is_staff=False)
    client.force_login(user)
    response = client.post(reverse("crm_softphone_session"))
    assert response.status_code == 403
    assert b"secret-token" not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("widget_on", "profile_on", "token", "why"),
    [
        (False, True, "tok", "виджет Новосистем выключен"),
        (True, False, "tok", "профиль выключен"),
        (True, True, "", "токен не задан"),
    ],
)
def test_session_refuses_when_phone_not_enabled(
    client: Any,
    django_user_model: Any,
    widget_on: bool,
    profile_on: bool,
    token: str,
    why: str,
) -> None:
    """Токен не выдаётся, пока виджет выключен, профиль выключен или токена нет."""
    _widget(enabled=widget_on)
    user = _staff(django_user_model, "agent", token=token, profile_enabled=profile_on)
    if not token and profile_on:
        StaffVpbxProfile.objects.create(user=user, uis_webrtc_token="", is_enabled=True)
    client.force_login(user)
    response = client.post(reverse("crm_softphone_session"))
    assert response.status_code == 403, why
    assert "token" not in response.json()


@pytest.mark.django_db
def test_session_refuses_unreadable_token(client: Any, django_user_model: Any) -> None:
    """Шифртекст не расшифровался (сменили ключ): отказ с пояснением, не пустой токен."""
    _widget()
    user = _staff(django_user_model, "agent", token="tok")
    StaffVpbxProfile.objects.filter(user=user).update(uis_webrtc_token="fernet1:not-a-valid-token")
    client.force_login(user)
    response = client.post(reverse("crm_softphone_session"))
    assert response.status_code == 403
    assert "token" not in response.json()
    assert "не читается" in response.json()["detail"]


# ── Окно «Телефон» ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_window_redirects_anonymous_to_admin_login(client: Any) -> None:
    """Аноним на окне телефона уходит на вход в админку."""
    response = client.get(reverse("crm_softphone_window"))
    assert response.status_code == 302
    assert reverse("admin:login") in response["Location"]


@pytest.mark.django_db
def test_window_forbids_non_staff(client: Any, django_user_model: Any) -> None:
    """Клиентский/нештатный аккаунт окно телефона не открывает."""
    user = _staff(django_user_model, "outsider", token="tok", is_staff=False)
    client.force_login(user)
    assert client.get(reverse("crm_softphone_window")).status_code == 403


@pytest.mark.django_db
def test_window_without_token_shows_blockers_and_no_library(client: Any, django_user_model: Any) -> None:
    """Сотруднику без токена окно объясняет причину и не грузит библиотеку звонков."""
    _widget()
    user = _staff(django_user_model, "agent")
    client.force_login(user)
    response = client.get(reverse("crm_softphone_window"))
    html = response.content.decode()
    assert response.status_code == 200
    assert "Токен WebRTC не задан" in html
    assert UIS_WEBRTC_LIB not in html
    assert 'data-blocked="1"' in html


@pytest.mark.django_db
def test_window_with_token_loads_library_but_never_embeds_token(client: Any, django_user_model: Any) -> None:
    """В HTML окна нет ни токена, ни шифртекста: токен приходит только POST-ом в память."""
    _widget()
    user = _staff(django_user_model, "agent", token="plain-token-xyz")
    stored = StaffVpbxProfile.objects.get(user=user).uis_webrtc_token
    client.force_login(user)
    response = client.get(reverse("crm_softphone_window"))
    html = response.content.decode()
    assert response.status_code == 200
    assert UIS_WEBRTC_LIB.rsplit("/", 1)[-1] in html
    assert "plain-token-xyz" not in html
    assert stored not in html
    assert 'data-blocked="0"' in html
    assert "no-store" in response.headers["Cache-Control"]


# ── Кто звонит: карточка по номеру в пределах прав ──────────────────────────


@pytest.mark.django_db
def test_lookup_finds_own_client_in_any_phone_format(client: Any, django_user_model: Any) -> None:
    """+7 (…)/8 …/7… — один и тот же клиент; у менеджера он свой."""
    _widget()
    manager = _staff(django_user_model, "mgr", token="tok", perms=("view_client",))
    mine = Client.objects.create(email="mine@example.test", name="Иван Петров", phone="79161112233", assignee=manager)
    client.force_login(manager)
    for raw in ("+7 (916) 111-22-33", "8 916 111 22 33", "79161112233"):
        body = client.get(reverse("crm_softphone_lookup"), {"phone": raw}).json()
        assert body["found"] is True, raw
        assert body["name"] == "Иван Петров"
        assert body["url"] == reverse("admin:crm_client_change", args=[mine.pk])


@pytest.mark.django_db
def test_lookup_hides_clients_of_other_managers(client: Any, django_user_model: Any) -> None:
    """Номер чужого клиента менеджеру не раскрывает ни имени, ни ссылки."""
    _widget()
    manager = _staff(django_user_model, "mgr", token="tok", perms=("view_client",))
    other = _staff(django_user_model, "other")
    Client.objects.create(email="theirs@example.test", name="Чужой Клиент", phone="79160000001", assignee=other)
    client.force_login(manager)
    response = client.get(reverse("crm_softphone_lookup"), {"phone": "79160000001"})
    assert response.json() == {"found": False}
    assert "Чужой" not in response.content.decode()


@pytest.mark.django_db
def test_lookup_requires_view_client_permission(client: Any, django_user_model: Any) -> None:
    """Без права просмотра клиентов поиск по номеру закрыт, даже для своего клиента."""
    _widget()
    manager = _staff(django_user_model, "mgr", token="tok")  # без view_client
    Client.objects.create(email="mine@example.test", name="Свой", phone="79161112233", assignee=manager)
    client.force_login(manager)
    response = client.get(reverse("crm_softphone_lookup"), {"phone": "79161112233"})
    assert response.status_code == 403
    assert "Свой" not in response.content.decode()


@pytest.mark.django_db
def test_lookup_requires_enabled_softphone(client: Any, django_user_model: Any) -> None:
    """Сотрудник без токена телефона этим адресом справочник клиентов не листает."""
    manager = _staff(django_user_model, "mgr", perms=("view_client",))
    Client.objects.create(email="mine@example.test", name="Свой", phone="79161112233", assignee=manager)
    client.force_login(manager)
    assert client.get(reverse("crm_softphone_lookup"), {"phone": "79161112233"}).status_code == 403


@pytest.mark.django_db
def test_lookup_ignores_short_numbers_and_merged_cards(client: Any, django_user_model: Any) -> None:
    """Добавочный (<5 цифр) и слитая (неактивная) карточка — «не найдено»."""
    _widget()
    manager = _staff(django_user_model, "mgr", token="tok", perms=("view_client",))
    Client.objects.create(
        email="merged@example.test", name="Слитый", phone="79165554433", assignee=manager, is_active=False
    )
    client.force_login(manager)
    assert client.get(reverse("crm_softphone_lookup"), {"phone": "101"}).json() == {"found": False}
    assert client.get(reverse("crm_softphone_lookup"), {"phone": "79165554433"}).json() == {"found": False}


# ── CSP: хосты UIS только у окна телефона ───────────────────────────────────


@pytest.mark.django_db
def test_csp_uis_hosts_only_on_softphone_window(client: Any, django_user_model: Any) -> None:
    """UIS и звуки data:/blob: разрешены только окну телефона; остальная админка и сайт — как были."""
    user = _staff(django_user_model, "agent", token="tok")
    client.force_login(user)

    window = _csp(client.get(reverse("crm_softphone_window")))
    assert "wss://*.uiscom.ru" in _directive(window, "connect-src")
    assert "https://*.uiscom.ru" in _directive(window, "connect-src")
    assert _directive(window, "media-src") == "media-src 'self' data: blob:"

    for path in ("/admin/", "/admin/login/", "/"):
        csp = _csp(client.get(path))
        assert "uiscom" not in csp, path
        assert _directive(csp, "media-src") == "media-src 'self'", path


def test_csp_softphone_path_matches_the_route() -> None:
    """Путь с особым CSP — именно тот, что отдаёт окно телефона (иначе CSP закроет окно)."""
    assert reverse("crm_softphone_window") == SOFTPHONE_PATH


# ── Подключение дока ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_dock_script_only_for_staff_with_phone(django_user_model: Any) -> None:
    """Скрипт дока получают только сотрудники с токеном при включённом виджете; остальным — пустой файл."""
    factory = RequestFactory()

    def script_for(user: Any) -> str:
        request = factory.get("/admin/")
        request.user = user
        return admin_softphone_js(request)

    _widget()
    with_token = _staff(django_user_model, "agent", token="tok")
    without = _staff(django_user_model, "plain")
    outsider = _staff(django_user_model, "outsider", token="tok", is_staff=False)

    assert "hoocon-softphone-dock.js" in script_for(with_token)
    assert "hoocon-noop.js" in script_for(without)
    assert "hoocon-noop.js" in script_for(outsider)

    _widget(enabled=False)
    assert "hoocon-noop.js" in script_for(with_token)


@pytest.mark.django_db
def test_admin_page_loads_dock_only_for_phone_users(client: Any, django_user_model: Any) -> None:
    """Реальная страница админки: у сотрудника с телефоном — док, у остальных — пустой скрипт."""
    _widget()
    with_token = _staff(django_user_model, "agent", token="tok")
    plain = _staff(django_user_model, "plain")

    client.force_login(with_token)
    html = client.get("/admin/").content.decode()
    assert "hoocon-softphone-dock.js" in html
    assert "hoocon-noop.js" not in html

    client.force_login(plain)
    html = client.get("/admin/").content.decode()
    assert "hoocon-softphone-dock.js" not in html
    assert "hoocon-noop.js" in html


def test_client_scripts_are_findable_and_consistent() -> None:
    """Все файлы телефона на месте, а док и окно говорят об одном и том же окне и канале."""
    for name in (
        "admin/js/hoocon-softphone-dock.js",
        "admin/js/hoocon-softphone-window.js",
        "admin/js/hoocon-noop.js",
        "admin/css/hoocon-softphone.css",
        UIS_WEBRTC_LIB,
    ):
        assert finders.find(name), name

    dock = (STATIC_JS / "hoocon-softphone-dock.js").read_text(encoding="utf-8")
    window = (STATIC_JS / "hoocon-softphone-window.js").read_text(encoding="utf-8")
    # source-lint: общий адрес окна и имя канала — одна договорённость между двумя файлами.
    assert f'"{SOFTPHONE_PATH}"' in dock
    assert 'CHANNEL = "hoocon-softphone"' in window
    assert 'new BroadcastChannel("hoocon-softphone")' in dock
    # source-lint: токен живёт только в памяти окна, не в хранилищах браузера.
    for source in (_code_only(dock), _code_only(window)):
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert "document.cookie" not in source


def test_dock_derives_a_stylesheet_url_that_exists() -> None:
    """Док вставляет <link> по адресу своего скрипта: после подстановки адрес обязан указывать на реальный CSS.

    Было: подстановка оставляла папку js/ — стили не грузились, док залипал внизу страницы без оформления.
    """
    dock = (STATIC_JS / "hoocon-softphone-dock.js").read_text(encoding="utf-8")
    # source-lint: достаём пару подстановки из кода дока и прогоняем её на настоящем URL скрипта.
    match = re.search(r'script\.src\.replace\("([^"]+)", "([^"]+)"\)', dock)
    assert match, "док должен выводить адрес CSS из адреса своего скрипта"
    script_url = _versioned_static("admin/js/hoocon-softphone-dock.js")
    css_url = script_url.replace(match.group(1), match.group(2))
    assert css_url != script_url
    css_path = urlsplit(css_url).path.removeprefix("/static/")
    assert finders.find(css_path), css_url


def test_dock_sits_above_the_sticky_save_bar() -> None:
    """Док лежит выше липкой панели «Сохранить» Unfold (≈65px = 4.06rem, z-index 110).

    Было: bottom 1rem + z-index 60 — на каждой форме правки док прятался под панелью и не нажимался.
    """
    css_path = finders.find("admin/css/hoocon-softphone.css")
    assert css_path
    css = Path(css_path).read_text(encoding="utf-8")
    # source-lint: геометрия подключаемого CSS; реальную раскладку смотрит смоук в браузере.
    rule = re.search(r"\n\.hsp-dock \{([^}]*)\}", css)
    assert rule, "нет правила .hsp-dock"
    bottom = re.search(r"bottom:\s*([\d.]+)rem", rule.group(1))
    assert bottom, "док должен иметь bottom в rem"
    save_bar_rem = 65 / 16
    assert float(bottom.group(1)) >= save_bar_rem + 0.5


def test_vendored_uis_library_is_the_published_build() -> None:
    """Файл библиотеки не подменён: sha256 билда @uiscom/uis_webrtc 2.0.2 (npm integrity сверен при вендоринге)."""
    path = finders.find(UIS_WEBRTC_LIB)
    assert path
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert digest == "50e8824c4fa4043d49624154879238afbb7da5ec88dde95c1e66ed57f927521f"


# ── Инлайн профиля: токен только на запись ──────────────────────────────────


def _form(profile: StaffVpbxProfile, **data: Any) -> StaffVpbxProfileForm:
    payload = {"extension": "", "uis_employee_id": "55", "is_enabled": "on", "uis_webrtc_token": ""}
    payload.update(data)
    return StaffVpbxProfileForm(data=payload, instance=profile)


@pytest.mark.django_db
def test_one_uis_employee_id_per_staff_user(django_user_model: Any) -> None:
    """Один ID UIS нельзя записать двум сотрудникам; пустой ID можно нескольким."""
    from django.db import IntegrityError

    owner = django_user_model.objects.create_user(
        username="uis-owner",
        email="uis-owner@example.test",
        password="password12",
    )
    other = django_user_model.objects.create_user(
        username="uis-other",
        email="uis-other@example.test",
        password="password12",
    )
    blank = django_user_model.objects.create_user(
        username="uis-blank",
        email="uis-blank@example.test",
        password="password12",
    )
    StaffVpbxProfile.objects.create(user=owner, uis_employee_id="3853967")
    StaffVpbxProfile.objects.create(user=blank, uis_employee_id="")
    StaffVpbxProfile.objects.create(
        user=django_user_model.objects.create_user(
            username="uis-blank-2",
            email="uis-blank-2@example.test",
            password="password12",
        ),
        uis_employee_id="",
    )

    form = _form(StaffVpbxProfile(user=other), uis_employee_id="3853967")
    assert not form.is_valid()
    assert "uis_employee_taken" in [error.code for error in form.errors["uis_employee_id"].as_data()]

    with pytest.raises(IntegrityError):
        StaffVpbxProfile.objects.create(user=other, uis_employee_id="3853967")


@pytest.mark.django_db
def test_profile_form_keeps_token_when_field_left_empty(django_user_model: Any) -> None:
    """Пустое поле токена при сохранении карточки сотрудника не стирает сохранённый токен."""
    user = _staff(django_user_model, "agent", token="keep-me")
    form = _form(StaffVpbxProfile.objects.get(user=user))
    assert form.is_valid(), form.errors
    form.save()
    assert StaffVpbxProfile.objects.get(user=user).uis_webrtc_token_plain == "keep-me"


@pytest.mark.django_db
def test_profile_form_replaces_and_clears_token(django_user_model: Any) -> None:
    """Новый токен заменяет старый; галочка «Удалить» очищает; оба сразу — отказ."""
    user = _staff(django_user_model, "agent", token="old-token")
    profile = StaffVpbxProfile.objects.get(user=user)

    form = _form(profile, uis_webrtc_token="  new-token  ")
    assert form.is_valid(), form.errors
    form.save()
    assert StaffVpbxProfile.objects.get(user=user).uis_webrtc_token_plain == "new-token"

    conflict = _form(StaffVpbxProfile.objects.get(user=user), uis_webrtc_token="x", clear_uis_webrtc_token="on")
    assert not conflict.is_valid()
    assert "token_conflict" in [e.code for e in conflict.non_field_errors().as_data()]
    assert StaffVpbxProfile.objects.get(user=user).uis_webrtc_token_plain == "new-token"

    clear = _form(StaffVpbxProfile.objects.get(user=user), clear_uis_webrtc_token="on")
    assert clear.is_valid(), clear.errors
    clear.save()
    assert StaffVpbxProfile.objects.get(user=user).uis_webrtc_token == ""


@pytest.mark.django_db
def test_user_admin_page_never_renders_token(client: Any, django_user_model: Any) -> None:
    """Страница пользователя в админке показывает «сохранён», но ни токена, ни шифртекста."""
    _widget()
    admin = django_user_model.objects.create_superuser(
        username="root", email="root@example.test", password="password12"
    )
    agent = _staff(django_user_model, "agent", token="plain-secret-777")
    stored = StaffVpbxProfile.objects.get(user=agent).uis_webrtc_token
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_change", args=[agent.pk]))
    html = response.content.decode()
    assert response.status_code == 200
    assert "plain-secret-777" not in html
    assert stored not in html
    assert "Сейчас: сохранён" in html
    assert "field-clear_uis_webrtc_token" not in html
    token = html.split("hoocon-token-field", 1)[1].split("</label>", 1)[0]
    assert "clear_uis_webrtc_token" in token
    assert "Удалить токен WebRTC" in token
    assert "телефон в браузере перестанет работать" in token
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8"
    )
    action = css.split(".hoocon-token-clear {", 1)[1].split("}", 1)[0]
    assert "display: inline-flex" in action
    assert "align-items: baseline" in action
