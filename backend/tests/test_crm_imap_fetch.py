"""Tests for crm.imap_fetch: IMAP → EmailMessage(inbound) → Client/Lead.

Фейковый IMAP (imaplib замокан), реальные email.message-письма байтами.
Покрытие: создание+привязка, дедуп по message_id, тред по In-Reply-To,
«Заявка #N» в теме, новый отправитель → заявка-консультация, вложения
в private media, курсор last_uid, disabled-флаг, Message-ID исходящих.
"""

from __future__ import annotations

import imaplib
from email.message import EmailMessage as StdEmailMessage
from typing import Any, ClassVar

import pytest
from django.conf import settings as django_settings
from django_celery_beat.models import PeriodicTask

from crm.imap_fetch import fetch_inbound_email
from crm.models import (
    Client,
    EmailAttachment,
    EmailDirection,
    EmailMessage,
    EmailStatus,
    InboundMailboxState,
)
from leads.models import Lead


def _raw_email(
    *,
    message_id: str = "<mail-1@example.test>",
    from_addr: str = "Buyer <buyer@example.test>",
    subject: str = "Вопрос",
    body: str = "Текст письма",
    in_reply_to: str | None = None,
    references: str | None = None,
    attachment: tuple[str, bytes] | None = None,
) -> bytes:
    """Build a raw RFC-822 message for the fake IMAP store."""
    msg = StdEmailMessage()
    msg["Message-ID"] = message_id
    msg["From"] = from_addr
    msg["To"] = "sales@hoocon.ru"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 06 Oct 2026 10:00:00 +0300"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    if attachment:
        fname, payload = attachment
        msg.add_attachment(
            payload,
            maintype="application",
            subtype="octet-stream",
            filename=fname,
        )
    return msg.as_bytes()


class _FakeIMAP:
    """Minimal imaplib.IMAP4_SSL stub over an in-memory UID store."""

    fail_logins: ClassVar[set[str]] = set()

    def __init__(self, host: str, port: int, *, messages: dict[int, bytes]) -> None:
        self._messages = messages

    def login(self, user: str, password: str) -> str:
        if user in self.fail_logins:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        return "OK"

    def select(self, folder: str, readonly: bool = True) -> tuple[str, list[bytes]]:
        return "OK", [b"1"]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "search":
            start = int(str(args[-1]).split(":")[0])
            found = sorted(uid for uid in self._messages if uid >= start)
            return "OK", [b" ".join(str(uid).encode() for uid in found)]
        if command == "fetch":
            uid = int(str(args[0]))
            return "OK", [(b"1 (UID)", self._messages[uid])]
        raise AssertionError(f"unexpected IMAP command {command}")

    def logout(self) -> str:
        return "OK"


_IMAP_CONNECT_TIMEOUTS: list[float | None] = []


@pytest.fixture()
def _imap(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    tmp_path: Any,
) -> dict[int, bytes]:
    """Enable IMAP with an empty fake store; silence staff notify."""
    store: dict[int, bytes] = {}
    settings.IMAP_ENABLED = True
    settings.IMAP_USE_SSL = True
    settings.IMAP_HOST = "imap.test"
    settings.IMAP_PORT = 993
    settings.IMAP_USER = "sales@hoocon.ru"
    settings.IMAP_PASSWORD = "secret"
    settings.IMAP_FETCH_LIMIT = 50
    # Storage резолвит settings при импорте модели — патчим location.
    storage = EmailAttachment._meta.get_field("file").storage
    monkeypatch.setattr(storage, "location", str(tmp_path / "private_media"))

    def _connect(host: str, port: int, *, timeout: float | None = None) -> _FakeIMAP:
        _IMAP_CONNECT_TIMEOUTS.append(timeout)
        return _FakeIMAP(host, port, messages=store)

    _IMAP_CONNECT_TIMEOUTS.clear()
    monkeypatch.setattr("crm.imap_fetch.imaplib.IMAP4_SSL", _connect)
    monkeypatch.setattr("crm.imap_fetch._notify_staff", lambda msg_row, box: None)
    return store


@pytest.mark.django_db
def test_fetch_creates_inbound_linked_to_existing_client(_imap: dict[int, bytes]) -> None:
    """From known client → inbound EmailMessage on that client, no new lead."""
    client = Client.objects.create(email="buyer@example.test", name="Buyer")
    _imap[11] = _raw_email(message_id="<m1@t>", subject="Привет")

    report = fetch_inbound_email()

    assert report == {"seen": 1, "created": 1, "duplicates": 0, "errors": 0}
    row = EmailMessage.objects.get(message_id="<m1@t>")
    assert row.client_id == client.pk
    assert row.direction == EmailDirection.INBOUND
    assert row.status == EmailStatus.RECEIVED
    assert row.lead_id is None  # клиент известен, треда нет — заявку не плодим
    assert row.imap_uid == 11
    assert row.received_at is not None
    assert InboundMailboxState.get_solo().last_uid == 11


@pytest.mark.django_db
def test_fetch_dedup_by_message_id(_imap: dict[int, bytes]) -> None:
    """Same Message-ID fetched twice → single row, second run counts dup."""
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[5] = _raw_email(message_id="<dup@t>")

    fetch_inbound_email()
    # Повторный poll: сервер отдаёт то же письмо (last_uid не защищает,
    # если курсор сброшен) — дедуп держит message_id unique.
    InboundMailboxState.objects.update(last_uid=0)
    report = fetch_inbound_email()

    assert report["duplicates"] == 1
    assert EmailMessage.objects.filter(message_id="<dup@t>").count() == 1


@pytest.mark.django_db
def test_fetch_links_thread_via_in_reply_to(_imap: dict[int, bytes]) -> None:
    """In-Reply-To → outbound message_id → lead of the thread."""
    client = Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="B",
        email="buyer@example.test",
        message="RFQ",
    )
    outbound = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.SENT,
        to_email="buyer@example.test",
        subject="КП",
        body="…",
        message_id="<crm-email-7@hoocon.ru>",
    )
    _imap[3] = _raw_email(
        message_id="<reply@t>",
        in_reply_to="<crm-email-7@hoocon.ru>",
        subject="Re: КП",
    )

    fetch_inbound_email()

    row = EmailMessage.objects.get(message_id="<reply@t>")
    assert row.lead_id == lead.pk == outbound.lead_id


@pytest.mark.django_db
def test_fetch_links_lead_by_subject_ref(_imap: dict[int, bytes]) -> None:
    """Тема «Re: Заявка #N» → привязка к заявке N без треда."""
    Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name="B",
        email="buyer@example.test",
        message="Вопрос",
    )
    _imap[9] = _raw_email(
        message_id="<subj@t>",
        subject=f"Re: Заявка #{lead.pk} — уточнение",
    )

    fetch_inbound_email()

    row = EmailMessage.objects.get(message_id="<subj@t>")
    assert row.lead_id == lead.pk


@pytest.mark.django_db
def test_subject_ref_ignored_for_foreign_sender(_imap: dict[int, bytes]) -> None:
    """M20: «Заявка #N» от чужого адреса не попадает в чужую заявку."""
    Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION, name="B", email="buyer@example.test", message="Вопрос"
    )
    _imap[11] = _raw_email(
        message_id="<spoof@t>",
        from_addr="Злоумышленник <evil@attacker.test>",
        subject=f"Re: Заявка #{lead.pk}",
    )

    fetch_inbound_email()

    row = EmailMessage.objects.get(message_id="<spoof@t>")
    assert row.lead_id != lead.pk
    assert row.client.email == "evil@attacker.test"


@pytest.mark.django_db
def test_thread_reference_ignored_for_foreign_sender(_imap: dict[int, bytes]) -> None:
    """M20: утёкший Message-ID исходящего не привязывает письмо чужого отправителя."""
    owner = Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(lead_type=Lead.LeadType.RFQ, name="B", email=owner.email, message="RFQ")
    EmailMessage.objects.create(
        client=owner,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.SENT,
        to_email=owner.email,
        subject="КП",
        body="…",
        message_id="<leaked@hoocon.ru>",
    )
    _imap[12] = _raw_email(
        message_id="<spoof2@t>",
        from_addr="Злоумышленник <evil2@attacker.test>",
        in_reply_to="<leaked@hoocon.ru>",
        subject="Re: КП",
    )

    fetch_inbound_email()

    assert EmailMessage.objects.get(message_id="<spoof2@t>").lead_id != lead.pk


@pytest.mark.django_db
def test_fetch_unknown_sender_creates_client_and_lead(_imap: dict[int, bytes]) -> None:
    """Новый отправитель → Client + заявка-консультация (письмо не теряется)."""
    _imap[2] = _raw_email(
        message_id="<new@t>",
        from_addr="Новый Клиент <newbie@corp.test>",
        subject="Нужен привод",
    )

    fetch_inbound_email()

    row = EmailMessage.objects.get(message_id="<new@t>")
    assert row.client.email == "newbie@corp.test"
    assert row.lead_id is not None
    lead = row.lead
    assert lead is not None
    assert lead.lead_type == Lead.LeadType.CONSULTATION
    lead.refresh_from_db()
    assert lead.client_id == row.client_id  # сигнал привязал карточку


@pytest.mark.django_db
def test_fetch_saves_attachment_in_private_media(
    _imap: dict[int, bytes],
    settings: Any,
) -> None:
    """Attachment → EmailAttachment; файл — вне public MEDIA_ROOT."""
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[4] = _raw_email(
        message_id="<att@t>",
        attachment=("spec.xlsx", b"XLSXDATA"),
    )

    fetch_inbound_email()

    att = EmailAttachment.objects.get(email__message_id="<att@t>")
    assert att.filename == "spec.xlsx"
    assert att.size == len(b"XLSXDATA")
    assert "private_media" in att.file.path
    assert f"{settings.MEDIA_ROOT}/" not in att.file.path
    assert att.file.read() == b"XLSXDATA"


@pytest.mark.django_db
def test_fetch_skips_poison_message_and_advances_cursor(
    _imap: dict[int, bytes],
) -> None:
    """Письмо без From → error в отчёте, курсор всё равно двигается."""
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[7] = _raw_email(message_id="<bad@t>", from_addr="")
    _imap[8] = _raw_email(message_id="<good@t>")

    report = fetch_inbound_email()

    assert report["errors"] == 1
    assert report["created"] == 1
    assert EmailMessage.objects.filter(message_id="<bad@t>").count() == 0
    assert InboundMailboxState.get_solo().last_uid == 8


def _flaky_fetch(monkeypatch: pytest.MonkeyPatch, *, uid: int, failures: int) -> None:
    """``_fetch_raw`` raises a network error for ``uid`` the first ``failures`` times."""
    from django.core.cache import cache

    from crm import imap_fetch

    cache.clear()
    real = imap_fetch._fetch_raw
    left = {"n": failures}

    def _fetch(conn: Any, current: int) -> bytes:
        if current == uid and left["n"] > 0:
            left["n"] -= 1
            raise OSError("connection reset")
        return real(conn, current)

    monkeypatch.setattr(imap_fetch, "_fetch_raw", _fetch)


@pytest.mark.django_db
def test_transient_error_keeps_cursor_before_failed_uid(
    _imap: dict[int, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Курсор уезжал за письмо при сетевой ошибке — письмо терялось навсегда."""
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[6] = _raw_email(message_id="<six@t>")
    _imap[7] = _raw_email(message_id="<seven@t>")
    _imap[8] = _raw_email(message_id="<eight@t>")
    _flaky_fetch(monkeypatch, uid=7, failures=1)

    first = fetch_inbound_email()
    state = InboundMailboxState.get_solo()
    assert first["created"] == 1 and first["errors"] == 1
    assert state.last_uid == 6
    assert "UID 7" in state.last_error

    second = fetch_inbound_email()
    assert second["created"] == 2
    assert set(EmailMessage.objects.values_list("message_id", flat=True)) == {"<six@t>", "<seven@t>", "<eight@t>"}
    assert InboundMailboxState.get_solo().last_error == ""


@pytest.mark.django_db
def test_transient_error_gives_up_after_retries(_imap: dict[int, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    """Вечно падающий UID не блокирует ящик: после 3 попыток курсор идёт дальше."""
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[7] = _raw_email(message_id="<stuck@t>")
    _imap[8] = _raw_email(message_id="<after@t>")
    _flaky_fetch(monkeypatch, uid=7, failures=99)

    fetch_inbound_email()
    fetch_inbound_email()
    assert InboundMailboxState.get_solo().last_uid == 0
    fetch_inbound_email()
    assert InboundMailboxState.get_solo().last_uid == 8
    assert EmailMessage.objects.filter(message_id="<after@t>").exists()


@pytest.mark.django_db
def test_long_message_id_stored_hashed_and_deduped(_imap: dict[int, bytes]) -> None:
    """Message-ID > 255 символов падал на INSERT, а курсор уходил дальше — письмо пропадало."""
    from crm.imap_fetch import normalize_message_id

    Client.objects.create(email="buyer@example.test", name="B")
    long_id = "<" + "x" * 300 + "@example.test>"
    _imap[3] = _raw_email(message_id=long_id, in_reply_to=long_id)

    assert fetch_inbound_email()["created"] == 1
    row = EmailMessage.objects.get()
    assert row.message_id == normalize_message_id(long_id)
    assert row.message_id.startswith("sha256:") and len(row.message_id) <= 255
    assert row.in_reply_to == row.message_id

    InboundMailboxState.objects.update(last_uid=0)
    assert fetch_inbound_email()["duplicates"] == 1
    assert normalize_message_id("<short@t>") == "<short@t>"


@pytest.mark.django_db
def test_fetch_disabled_returns_skipped(settings: Any) -> None:
    """IMAP_ENABLED=false → задача выходит без подключения."""
    settings.IMAP_ENABLED = False
    assert fetch_inbound_email() == {"skipped": 1}
    assert EmailMessage.objects.count() == 0


@pytest.mark.django_db
def test_beat_periodic_task_registered() -> None:
    """Миграция создаёт PeriodicTask — регресс на beat-расписание."""
    task = PeriodicTask.objects.get(name="crm.fetch_inbound_email")
    assert task.enabled is True
    assert task.task == "crm.fetch_inbound_email"


@pytest.mark.django_db
def test_outbound_send_stamps_message_id() -> None:
    """Исходящее получает Message-ID — ключ будущего In-Reply-To клиента."""
    from crm.tasks import send_crm_email

    client = Client.objects.create(email="buyer@example.test", name="B")
    row = EmailMessage.objects.create(
        client=client,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        subject="КП",
        body="…",
    )

    send_crm_email.run(row.pk)

    row.refresh_from_db()
    assert row.status == EmailStatus.SENT
    assert row.message_id.startswith("<")
    assert row.message_id.endswith(f".crm-email-{row.pk}@{row.from_email.split('@')[-1]}>")


@pytest.mark.django_db
def test_outbound_message_id_not_guessable() -> None:
    """M20: Message-ID исходящих случайный — по номеру письма его не угадать."""
    from crm.tasks import send_crm_email

    client = Client.objects.create(email="guess@example.test", name="B")
    ids = []
    for _ in range(2):
        row = EmailMessage.objects.create(
            client=client,
            direction=EmailDirection.OUTBOUND,
            status=EmailStatus.QUEUED,
            to_email=client.email,
            from_email="noreply@hoocon.ru",
            subject="КП",
            body="…",
        )
        send_crm_email.run(row.pk)
        row.refresh_from_db()
        assert row.message_id != f"<crm-email-{row.pk}@hoocon.ru>"
        ids.append(row.message_id)
    assert ids[0] != ids[1]


def _staff_user(username: str = "mgr") -> Any:
    """Staff user — владелец личного ящика."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
    )


@pytest.mark.django_db
def test_staff_mailbox_fetched_when_env_disabled(
    _imap: dict[int, bytes],
    settings: Any,
) -> None:
    """Личный ящик менеджера опрашивается даже без общего IMAP_ENABLED."""
    from accounts.models import StaffMailbox

    settings.IMAP_ENABLED = False
    owner = _staff_user()
    mailbox = StaffMailbox.objects.create(
        user=owner,
        imap_user="ivan@hoocon.ru",
        imap_password="app-not-secret",
    )
    _imap[4] = _raw_email(
        message_id="<staff@t>",
        from_addr="Клиент <cl@corp.test>",
        subject="Нужен привод",
    )

    report = fetch_inbound_email()

    assert report["created"] == 1
    row = EmailMessage.objects.get(message_id="<staff@t>")
    assert row.mailbox_id == mailbox.pk
    assert row.to_email == "ivan@hoocon.ru"
    # новый отправитель → заявка-консультация сразу на владельце ящика,
    # клиент тоже закрепляется за ним
    assert row.lead is not None
    assert row.lead.assignee_id == owner.pk
    assert row.client.assignee_id == owner.pk
    mailbox.refresh_from_db()
    assert mailbox.last_uid == 4


@pytest.mark.django_db
def test_same_message_in_two_boxes_deduped(
    _imap: dict[int, bytes],
) -> None:
    """Письмо в общем и личном ящике → одна строка (дедуп по Message-ID)."""
    from accounts.models import StaffMailbox

    StaffMailbox.objects.create(
        user=_staff_user(),
        imap_user="ivan@hoocon.ru",
        imap_password="app-not-secret",
    )
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[6] = _raw_email(message_id="<both@t>")

    report = fetch_inbound_email()

    assert report["seen"] == 2
    assert report["created"] == 1
    assert report["duplicates"] == 1
    assert EmailMessage.objects.filter(message_id="<both@t>").count() == 1


@pytest.mark.django_db
def test_broken_mailbox_does_not_block_others(
    _imap: dict[int, bytes],
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ошибка логина в один ящик → last_error там, остальные работают."""
    from accounts.models import StaffMailbox

    settings.IMAP_ENABLED = False
    bad = StaffMailbox.objects.create(
        user=_staff_user("bad"),
        imap_user="bad@hoocon.ru",
        imap_password="expired",
    )
    good = StaffMailbox.objects.create(
        user=_staff_user("good"),
        imap_user="good@hoocon.ru",
        imap_password="app-not-secret",
    )
    monkeypatch.setattr(_FakeIMAP, "fail_logins", {"bad@hoocon.ru"})
    _imap[3] = _raw_email(message_id="<ok@t>")

    report = fetch_inbound_email()

    assert report["errors"] == 1
    assert report["created"] == 1
    assert EmailMessage.objects.get(message_id="<ok@t>").mailbox_id == good.pk
    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.last_error  # ошибка записана на ящике
    assert bad.last_uid == 0
    assert good.last_uid == 3
    assert good.last_error == ""


@pytest.mark.django_db
def test_disabled_staff_mailbox_skipped(
    _imap: dict[int, bytes],
    settings: Any,
) -> None:
    """is_enabled=False → ящик не опрашивается, ничего не создаётся."""
    from accounts.models import StaffMailbox

    settings.IMAP_ENABLED = False
    StaffMailbox.objects.create(
        user=_staff_user(),
        imap_user="ivan@hoocon.ru",
        imap_password="app-not-secret",
        is_enabled=False,
    )
    _imap[1] = _raw_email(message_id="<off@t>")

    assert fetch_inbound_email() == {"skipped": 1}
    assert EmailMessage.objects.count() == 0


@pytest.mark.django_db
def test_mailbox_scope_owner_sees_own_mail(
    _imap: dict[int, bytes],
    settings: Any,
) -> None:
    """Менеджер видит входящие из своего ящика через scope_emails."""
    from accounts.models import StaffMailbox
    from crm.services import scope_emails_for_manager

    settings.IMAP_ENABLED = False
    owner = _staff_user("owner")
    other = _staff_user("other")
    mailbox = StaffMailbox.objects.create(
        user=owner,
        imap_user="owner@hoocon.ru",
        imap_password="p",
    )
    Client.objects.create(email="buyer@example.test", name="B")
    _imap[5] = _raw_email(message_id="<own@t>")
    fetch_inbound_email()
    row = EmailMessage.objects.get(message_id="<own@t>")
    assert row.mailbox_id == mailbox.pk

    assert row in scope_emails_for_manager(EmailMessage.objects.all(), owner)
    assert row not in scope_emails_for_manager(EmailMessage.objects.all(), other)


@pytest.mark.django_db
def test_new_client_company_guessed_from_corporate_domain(
    _imap: dict[int, bytes],
) -> None:
    """Корпоративный домен → company карточки; бесплатный — нет.

    company_key карточки тогда матчится owner-правилами (pinned-rule /
    sticky-владелец), а менеджер при необходимости правит юрлицо руками.
    """
    _imap[1] = _raw_email(
        message_id="<corp@t>",
        from_addr="Иван <i.petrov@romashka.test>",
    )
    _imap[2] = _raw_email(
        message_id="<free@t>",
        from_addr="Петя <petr@gmail.com>",
    )

    fetch_inbound_email()

    corp = EmailMessage.objects.get(message_id="<corp@t>")
    free = EmailMessage.objects.get(message_id="<free@t>")
    assert corp.client.company == "romashka.test"
    assert corp.client.company_key == "romashka.test"
    assert corp.lead is not None
    corp.lead.refresh_from_db()
    assert corp.lead.company == "romashka.test"  # заявка тоже с компанией
    assert free.client.company == ""


@pytest.mark.django_db
def test_env_box_routes_via_canonical_pipeline(
    _imap: dict[int, bytes],
) -> None:
    """Общий ящик + новый отправитель → канонический assign_lead_on_create:
    round-robin по группе «Менеджер», клиент закрепляется за ним."""
    from django.contrib.auth.models import Group

    from accounts.roles import GROUP_MANAGER
    from sitesettings.models import SiteSettings

    group = Group.objects.get(name=GROUP_MANAGER)
    m1 = _staff_user("m1")
    m2 = _staff_user("m2")
    m1.groups.add(group)
    m2.groups.add(group)
    site = SiteSettings.load()
    site.lead_routing_mode = SiteSettings.LeadRoutingMode.ASSIGN_MANAGER
    site.lead_rr_last_user = None
    site.save(update_fields=["lead_routing_mode", "lead_rr_last_user", "updated_at"])
    _imap[1] = _raw_email(message_id="<d1@t>", from_addr="Новый <n1@alpha.test>")
    _imap[2] = _raw_email(message_id="<d2@t>", from_addr="Другой <n2@beta.test>")

    fetch_inbound_email()

    row1 = EmailMessage.objects.get(message_id="<d1@t>")
    row2 = EmailMessage.objects.get(message_id="<d2@t>")
    assert row1.lead is not None and row2.lead is not None
    assert row1.lead.assignee_id == m1.pk
    assert row1.client.assignee_id == m1.pk  # компания закреплена
    assert row2.lead.assignee_id == m2.pk  # следующий по кругу


@pytest.mark.django_db
def test_routing_off_keeps_shared_pool(
    _imap: dict[int, bytes],
) -> None:
    """lead_routing_mode=off (дефолт) → заявка в общий пул (assignee=None)."""
    _imap[1] = _raw_email(message_id="<np@t>", from_addr="Новый <n@corp.test>")

    fetch_inbound_email()

    row = EmailMessage.objects.get(message_id="<np@t>")
    assert row.lead is not None
    assert row.lead.assignee_id is None


@pytest.mark.django_db
def test_mailbox_form_keeps_password_on_empty_input() -> None:
    """Пустое поле пароля в Admin-форме не затирает сохранённый пароль."""
    from accounts.forms import StaffMailboxForm
    from accounts.models import StaffMailbox

    mailbox = StaffMailbox.objects.create(
        user=_staff_user(),
        imap_user="ivan@hoocon.ru",
        imap_password="old-not-secret",
    )
    form = StaffMailboxForm(
        data={
            "user": str(mailbox.user_id),
            "imap_user": "ivan@hoocon.ru",
            "imap_password": "",
            "folder": "INBOX",
            "smtp_host": "smtp.yandex.ru",
            "smtp_port": "465",
            "smtp_use_ssl": "on",
            "is_enabled": "on",
            "last_uid": "0",
        },
        instance=mailbox,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.imap_password_plain == "old-not-secret"
    assert saved.imap_password != "old-not-secret"


@pytest.mark.django_db
def test_mailbox_password_roundtrip_survives_save() -> None:
    """Plain app passwords are encrypted at rest and decrypt for IMAP."""
    from accounts.mailbox_secrets import decrypt_mailbox_secret, encrypt_mailbox_secret
    from accounts.models import StaffMailbox

    mailbox = StaffMailbox.objects.create(
        user=_staff_user(),
        imap_user="roundtrip@hoocon.ru",
        imap_password="app-not-secret-1",
    )
    mailbox.refresh_from_db()
    assert mailbox.imap_password.startswith("fernet1:")
    assert decrypt_mailbox_secret(mailbox.imap_password) == "app-not-secret-1"
    assert encrypt_mailbox_secret(mailbox.imap_password) == mailbox.imap_password


@pytest.mark.django_db
def test_mailbox_password_unreadable_from_db_dump() -> None:
    """Регресс: signing.dumps — это base64, пароль читался из дампа БД без ключа."""
    import base64

    from accounts.models import StaffMailbox

    mailbox = StaffMailbox.objects.create(
        user=_staff_user(),
        imap_user="dump@hoocon.ru",
        imap_password="app-not-secret-2",
    )
    stored = StaffMailbox.objects.values_list("imap_password", flat=True).get(pk=mailbox.pk)
    token = stored.split(":", 1)[1]
    blob = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert b"app-not-secret-2" not in blob
    assert "app-not-secret-2" not in stored


@pytest.mark.django_db
def test_legacy_signed_mailbox_password_upgrades_on_save() -> None:
    """Старые строки signed1: читаются и при сохранении переходят на Fernet."""
    from django.core.signing import dumps

    from accounts.mailbox_secrets import decrypt_mailbox_secret
    from accounts.models import StaffMailbox

    legacy = "signed1:" + dumps("legacy-pass", salt="hoocon.staff-mailbox.imap", compress=True)
    assert decrypt_mailbox_secret(legacy) == "legacy-pass"
    mailbox = StaffMailbox.objects.create(user=_staff_user(), imap_user="l@hoocon.ru", imap_password=legacy)
    mailbox.refresh_from_db()
    assert mailbox.imap_password.startswith("fernet1:")
    assert mailbox.imap_password_plain == "legacy-pass"


def test_legacy_signed_bad_signature_preserved_not_wiped() -> None:
    """Bugbot: rotated SECRET_KEY made _decode_legacy return '' → encrypt persisted ''."""
    from accounts.mailbox_secrets import encrypt_mailbox_secret

    corrupted = "signed1:INVALID_PAYLOAD_THAT_CANNOT_VERIFY"
    result = encrypt_mailbox_secret(corrupted)
    assert result == corrupted, "Bad-signature legacy token must stay intact, not become ''"


def test_mailbox_password_uses_explicit_key(settings: Any) -> None:
    """MAILBOX_ENCRYPTION_KEY отделяет ключ ящиков от SECRET_KEY."""
    from cryptography.fernet import Fernet

    from accounts.mailbox_secrets import decrypt_mailbox_secret, encrypt_mailbox_secret

    settings.MAILBOX_ENCRYPTION_KEY = Fernet.generate_key().decode()
    sealed = encrypt_mailbox_secret("k-pass")
    assert decrypt_mailbox_secret(sealed) == "k-pass"
    settings.MAILBOX_ENCRYPTION_KEY = Fernet.generate_key().decode()
    assert decrypt_mailbox_secret(sealed) == ""


class _FakeConnection:
    """SMTP backend stub: captures sent messages."""

    def __init__(self) -> None:
        self.sent: list[Any] = []

    def send_messages(self, messages: list[Any]) -> int:
        self.sent.extend(messages)
        return len(messages)


@pytest.mark.django_db
def test_outbound_sends_via_personal_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Письмо с mailbox → отправка через SMTP-креды этого ящика.

    From принудительно = адрес ящика (Яндекс отклоняет чужой From),
    ответ клиента по In-Reply-To придёт в тот же личный ящик.
    """
    from accounts.models import StaffMailbox
    from crm.tasks import send_crm_email

    owner = _staff_user("ivan")
    mailbox = StaffMailbox.objects.create(
        user=owner,
        imap_user="ivan@hoocon.ru",
        imap_password="app-not-secret",
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_use_ssl=False,
    )
    client = Client.objects.create(email="buyer@example.test", name="B")
    row = EmailMessage.objects.create(
        client=client,
        mailbox=mailbox,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        subject="КП",
        body="…",
    )
    conn = _FakeConnection()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "crm.tasks.get_connection",
        lambda **kw: calls.append(kw) or conn,
    )

    send_crm_email.run(row.pk)

    assert calls == [
        {
            "host": "smtp.test",
            "port": 587,
            "username": "ivan@hoocon.ru",
            "password": "app-not-secret",
            "use_ssl": False,
            "use_tls": True,
            "timeout": django_settings.EMAIL_TIMEOUT,
            "fail_silently": False,
        }
    ]
    assert len(conn.sent) == 1
    sent = conn.sent[0]
    assert sent.from_email == "ivan@hoocon.ru"
    row.refresh_from_db()
    assert row.from_email == "ivan@hoocon.ru"  # в досье — реальный отправитель
    assert row.status == EmailStatus.SENT


@pytest.mark.django_db
def test_outbound_without_mailbox_uses_default_backend(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """Без mailbox → личный get_connection не вызывается, общий backend."""
    from django.core import mail as dj_mail

    from crm.tasks import send_crm_email

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client = Client.objects.create(email="buyer@example.test", name="B")
    row = EmailMessage.objects.create(
        client=client,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        subject="КП",
        body="…",
    )
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "crm.tasks.get_connection",
        lambda **kw: calls.append(kw),
    )

    send_crm_email.run(row.pk)

    assert calls == []  # личное подключение не строилось
    assert len(dj_mail.outbox) == 1
    row.refresh_from_db()
    assert row.status == EmailStatus.SENT


@pytest.mark.django_db
def test_create_outbound_uses_author_mailbox(settings) -> None:
    """create_outbound_email: у автора с ящиком From = его адрес + mailbox."""
    from accounts.models import StaffMailbox
    from crm.services import create_outbound_email

    settings.DEFAULT_FROM_EMAIL = "sales@hoocon.ru"

    owner = _staff_user("ivan2")
    mailbox = StaffMailbox.objects.create(
        user=owner,
        imap_user="ivan2@hoocon.ru",
        imap_password="app-not-secret",
    )
    stranger = _staff_user("petr")  # без ящика — общий отправитель
    client = Client.objects.create(email="buyer@example.test", name="B")

    own = create_outbound_email(
        client=client,
        subject="КП",
        body="…",
        author=owner,
        send_now=False,
    )
    shared = create_outbound_email(
        client=client,
        subject="КП2",
        body="…",
        author=stranger,
        send_now=False,
    )

    assert own.mailbox_id == mailbox.pk
    assert own.from_email == "ivan2@hoocon.ru"
    assert shared.mailbox_id is None
    assert shared.from_email == "sales@hoocon.ru"  # общий DEFAULT_FROM_EMAIL


@pytest.mark.django_db
def test_lead_reply_via_own_mailbox_no_bcc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ответ из личного ящика менеджера → без BCC себе.

    Копия и так лежит в «Отправленных» этого ящика; BCC создал бы
    дубль во «Входящих».
    """
    from accounts.models import StaffMailbox
    from crm.tasks import send_crm_email

    owner = _staff_user("bcc-own")
    mailbox = StaffMailbox.objects.create(
        user=owner,
        imap_user="bcc-own@hoocon.ru",
        imap_password="x-not-secret",
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_use_ssl=False,
    )
    client = Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="B",
        email="buyer@example.test",
        message="RFQ",
    )
    row = EmailMessage.objects.create(
        client=client,
        lead=lead,
        mailbox=mailbox,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        reply_to_email="bcc-own@hoocon.ru",
        subject="Ответ",
        body="…",
    )
    conn = _FakeConnection()
    monkeypatch.setattr("crm.tasks.get_connection", lambda **kw: conn)

    send_crm_email.run(row.pk)

    assert len(conn.sent) == 1
    sent = conn.sent[0]
    assert sent.from_email == "bcc-own@hoocon.ru"
    assert sent.reply_to == ["bcc-own@hoocon.ru"]
    assert not sent.bcc  # менеджеру дубля в «Входящие» не уходит


@pytest.mark.django_db
def test_lead_reply_via_shared_mailbox_bcc_manager(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """Ответ через общий ящик → ровно один BCC менеджеру.

    Тред стартует в его ящике одной копией; повторная выборка IMAP
    отсекается дедупом по message_id.
    """
    from django.core import mail as dj_mail

    from crm.tasks import send_crm_email

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client = Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="B",
        email="buyer@example.test",
        message="RFQ",
    )
    row = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        reply_to_email="mgr@hoocon.ru",
        subject="Ответ",
        body="…",
    )

    send_crm_email.run(row.pk)

    assert len(dj_mail.outbox) == 1
    sent = dj_mail.outbox[0]
    assert sent.bcc == ["mgr@hoocon.ru"]  # одна копия, не массив дублей
    assert sent.reply_to == ["mgr@hoocon.ru"]


@pytest.mark.django_db
def test_lead_reply_no_bcc_when_reply_to_is_client(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    """reply_to == адресу клиента → BCC не ставится (не дублируем клиенту)."""
    from django.core import mail as dj_mail

    from crm.tasks import send_crm_email

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client = Client.objects.create(email="buyer@example.test", name="B")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="B",
        email="buyer@example.test",
        message="RFQ",
    )
    row = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED,
        to_email="buyer@example.test",
        from_email="noreply@hoocon.ru",
        reply_to_email="buyer@example.test",
        subject="Ответ",
        body="…",
    )

    send_crm_email.run(row.pk)

    assert len(dj_mail.outbox) == 1
    assert not dj_mail.outbox[0].bcc


@pytest.mark.django_db
def test_imap_connect_uses_timeout(_imap: dict[int, bytes], settings: Any) -> None:
    """M35: IMAP без timeout вешал воркер Celery навсегда (concurrency 2 → OTP/чат стоят)."""
    settings.IMAP_TIMEOUT = 17
    fetch_inbound_email()
    assert _IMAP_CONNECT_TIMEOUTS == [17]


@pytest.mark.django_db
def test_fetch_task_skips_when_previous_run_holds_lock(_imap: dict[int, bytes]) -> None:
    """M35: медленный опрос IMAP не перекрывается следующим запуском beat."""
    from django.core.cache import cache

    from crm.tasks import _IMAP_FETCH_LOCK
    from crm.tasks import fetch_inbound_email as fetch_task

    cache.add(_IMAP_FETCH_LOCK, 1, timeout=60)
    try:
        assert fetch_task.run() == "locked"
        assert _IMAP_CONNECT_TIMEOUTS == []
    finally:
        cache.delete(_IMAP_FETCH_LOCK)

    assert fetch_task.run().startswith("seen=")
    assert cache.get(_IMAP_FETCH_LOCK) is None


@pytest.mark.django_db
def test_personal_smtp_connection_has_timeout(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """M35: личный SMTP менеджера тоже с timeout (EMAIL_TIMEOUT)."""
    from accounts.models import StaffMailbox
    from crm.tasks import _smtp_connection_for

    settings.EMAIL_TIMEOUT = 23
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("crm.tasks.get_connection", lambda **kw: calls.append(kw) or object())
    user = _staff_user("smtp-mgr")
    box = StaffMailbox.objects.create(
        user=user, imap_user="mgr@hoocon.ru", imap_password="pw", smtp_host="smtp.test", smtp_port=465
    )
    row = EmailMessage(mailbox=box, direction=EmailDirection.OUTBOUND, to_email="c@x.test")

    assert _smtp_connection_for(row) is not None
    assert calls[0]["timeout"] == 23


def test_celery_has_global_time_limits() -> None:
    """M35: глобальные soft/hard лимиты задач подхватываются приложением Celery."""
    from config.celery import app

    assert app.conf.task_soft_time_limit and app.conf.task_time_limit
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit
