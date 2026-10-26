"""Regressions for the confirmed items in the 2026-10 review."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils import timezone

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_public_lead_rejects_call_stub_email(client) -> None:
    """Форма сайта с @call.invalid не становится карточкой «Звонок пропущен»."""
    from crm.models import Client

    response = client.post(
        "/api/leads/",
        data={
            "pdn_consent": True,
            "name": "Бот",
            "email": "79991234567@call.invalid",
            "company": "Пустышка",
            "message": "Это не звонок, это форма.",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not Client.objects.filter(email__iendswith="@call.invalid").exists()


@pytest.mark.django_db
def test_search_nul_is_bad_request_not_server_error(client) -> None:
    """NUL в поиске — 400, а не 500 с алертом в Telegram."""
    response = client.get("/api/search/", {"q": "\x00"})
    assert response.status_code == 400


def test_query_int_rejects_unicode_digits() -> None:
    """«²».isdigit() истинно, int() падает. Идентификатор из query так не разбирается."""
    from config.query_int import query_int

    assert query_int("²") is None
    assert query_int("12") == 12
    assert query_int("12\x00") is None


def test_uis_infinite_talk_duration_is_zero() -> None:
    """int(float('inf')) — OverflowError, вебхук UIS не должен отвечать 500."""
    from crm.novosystem import _talk_seconds

    assert _talk_seconds(float("inf")) == 0
    assert _talk_seconds("inf") == 0


@pytest.mark.django_db
def test_stale_queued_email_is_handed_back_to_the_broker() -> None:
    """QUEUED старше окна отправки ставится в брокер снова. Свежая отправка — нет."""
    from crm.models import Client, EmailMessage, EmailStatus
    from crm.tasks import _EMAIL_SEND_STAMP, requeue_stale_crm_emails, send_crm_email

    assert send_crm_email.acks_late is True
    person = Client.objects.create(name="Анна", email="anna@client.test")
    stuck = EmailMessage.objects.create(
        client=person,
        to_email="anna@client.test",
        subject="КП",
        body="Текст",
        status=EmailStatus.QUEUED,
    )
    cache.set(
        _EMAIL_SEND_STAMP.format(pk=stuck.pk),
        (timezone.now() - timedelta(hours=1)).timestamp(),
        timeout=3600,
    )
    with patch("crm.tasks.send_crm_email.delay") as delay:
        assert requeue_stale_crm_emails() == 1
    delay.assert_called_once_with(stuck.pk)

    cache.set(_EMAIL_SEND_STAMP.format(pk=stuck.pk), timezone.now().timestamp(), timeout=3600)
    with patch("crm.tasks.send_crm_email.delay") as delay:
        assert requeue_stale_crm_emails() == 0
    delay.assert_not_called()


@pytest.mark.django_db
def test_crash_after_smtp_does_not_send_a_second_copy(settings) -> None:
    """Воркер умер после SMTP и до «отправлено» — второе письмо не уходит, очередь его не ставит."""
    from django.core import mail

    from crm.models import Client, EmailMessage, EmailStatus
    from crm.tasks import _EMAIL_SEND_STAMP, requeue_stale_crm_emails, send_crm_email

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    person = Client.objects.create(name="Анна", email="anna-once@client.test")
    msg = EmailMessage.objects.create(
        client=person,
        to_email="anna-once@client.test",
        subject="КП",
        body="Текст",
        status=EmailStatus.QUEUED,
    )
    cache.set(
        _EMAIL_SEND_STAMP.format(pk=msg.pk),
        (timezone.now() - timedelta(hours=1)).timestamp(),
        timeout=3600,
    )

    def _die(self: object) -> None:
        raise RuntimeError("worker lost after smtp")

    with patch("crm.models.EmailMessage.mark_sent", _die):
        with pytest.raises(RuntimeError, match="worker lost after smtp"):
            send_crm_email.run(msg.pk)

    msg.refresh_from_db()
    assert msg.status == EmailStatus.SENDING
    assert len(mail.outbox) == 1
    with patch("crm.tasks.send_crm_email.delay") as delay:
        assert requeue_stale_crm_emails() == 0
    delay.assert_not_called()
    send_crm_email.run(msg.pk)
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_manager_can_requeue_a_stale_sending_row(client, django_user_model) -> None:
    """Кнопка снова ставит «Отправку» старше окна и не трогает ту, что ещё в пути."""
    from django.urls import reverse

    from crm.models import Client, EmailMessage, EmailStatus
    from crm.tasks import _EMAIL_SEND_STAMP

    user = django_user_model.objects.create_user(
        username="crm-resend",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    person = Client.objects.create(name="Борис", email="boris-send@client.test")
    stuck = EmailMessage.objects.create(
        client=person,
        to_email="boris-send@client.test",
        subject="Застряло",
        body="Текст",
        status=EmailStatus.SENDING,
    )
    fresh = EmailMessage.objects.create(
        client=person,
        to_email="boris-send@client.test",
        subject="В пути",
        body="Текст",
        status=EmailStatus.SENDING,
    )
    cache.set(
        _EMAIL_SEND_STAMP.format(pk=stuck.pk),
        (timezone.now() - timedelta(hours=1)).timestamp(),
        timeout=3600,
    )
    cache.set(_EMAIL_SEND_STAMP.format(pk=fresh.pk), timezone.now().timestamp(), timeout=3600)
    client.force_login(user)
    with patch("crm.tasks.send_crm_email.delay") as delay:
        response = client.post(
            reverse("admin:crm_emailmessage_changelist"),
            {"action": "queue_send", "_selected_action": [str(stuck.pk), str(fresh.pk)]},
        )
    assert response.status_code in {200, 302}
    delay.assert_called_once_with(stuck.pk)
    stuck.refresh_from_db()
    fresh.refresh_from_db()
    assert stuck.status == EmailStatus.QUEUED
    assert fresh.status == EmailStatus.SENDING


@pytest.mark.django_db
def test_cabinet_pdf_hides_prices_when_the_flag_is_off(settings) -> None:
    """Генератор PDF не рисует цену и «Итого», когда кабинет просит скрыть цены."""
    from decimal import Decimal

    from crm.models import Client, Quote, QuoteItem, QuoteStatus
    from crm.quote_pdf import render_quote_pdf
    from tests.quote_pdf_text import pdf_text

    settings.CABINET_SHOW_PRICES = False
    person = Client.objects.create(name="Клиент", email="pdf-price@acme.test", company="Акме")
    quote = Quote.objects.create(client=person, status=QuoteStatus.SENT, number="КП-9")
    QuoteItem.objects.create(quote=quote, sku_code="DA-1", quantity=1, unit_price=Decimal("1234.50"))

    hidden = pdf_text(render_quote_pdf(quote, include_prices=False))
    assert "1234.50" not in hidden
    assert "Итого" not in hidden

    shown = pdf_text(render_quote_pdf(quote, include_prices=True))
    assert "1234.50" in shown
    assert "Итого" in shown


@pytest.mark.django_db
def test_rma_photo_requires_view_permission(client, django_user_model) -> None:
    """Скачивание фото рекламации без view_rmacase — 403, как у соседних файлов."""
    from cabinet.models import RmaCase
    from crm.models import Client

    person = Client.objects.create(name="Клиент", email="rma-photo@acme.test")
    case = RmaCase.objects.create(client=person, subject="Гудит")
    staff = django_user_model.objects.create_user(
        username="rma-outsider",
        password="test-pass-not-secret",
        is_staff=True,
    )
    client.force_login(staff)
    response = client.get(f"/admin/cabinet/rmacase/{case.pk}/photo/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_manual_refresh_does_not_publish_a_non_pdf() -> None:
    """ETL не кладёт на сайт файл без PDF-magic, даже если имя заканчивается на .pdf."""
    from catalog.etl.file_refresh import publishable_pdf, refresh_product_file
    from catalog.models import SKU, Category, Product, ProductFile

    assert publishable_pdf("note.pdf", b"not a pdf") is False
    category = Category.objects.create(name="Воздух", slug="air-pdf-guard")
    product = Product.objects.create(name="HVA", slug="hva-pdf-guard", category=category)
    sku = SKU.objects.create(product=product, name="HVA", slug="hva-pdf-guard-sku", sku_code="HVA-PDF-GUARD")
    row = ProductFile(sku=sku, title="Инструкция", file_type=ProductFile.FileType.DATASHEET, is_published=True)
    row.file.save("manual.pdf", ContentFile(b"%PDF-1.4\n"), save=True)
    assert refresh_product_file(row, basename="manual.pdf", payload=b"not a pdf") is False
    with row.file.open("rb") as handle:
        assert handle.read().startswith(b"%PDF")


@pytest.mark.django_db
def test_mask_copied_production_secrets_clears_tokens() -> None:
    """Копия продовой базы не оставляет боевые токены бота и АТС на ноутбуке."""
    from django.contrib.sessions.models import Session

    from sitesettings.mask_synced_secrets import mask_copied_production_secrets
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_bot_token = "123456:live"
    site.novosystem_webhook_secret = "uis-secret"
    site.mango_api_key = "mango-live-key"
    site.mango_api_salt = "mango-live-salt"
    site.save()
    Session.objects.create(session_key="a" * 32, session_data="x", expire_date=timezone.now() + timedelta(days=1))
    report = mask_copied_production_secrets()
    site.refresh_from_db()
    assert site.telegram_bot_token == ""
    assert site.novosystem_webhook_secret == ""
    assert site.mango_api_key == ""
    assert site.mango_api_salt == ""
    assert report["sessions"] == 1
    assert Session.objects.count() == 0


@pytest.mark.django_db
def test_mask_copied_production_secrets_refuses_a_remote_database() -> None:
    """Зачистка токенов не запускается, если Django смотрит не на локальную базу."""
    from sitesettings.mask_synced_secrets import mask_copied_production_secrets
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_bot_token = "123456:live"
    site.save()
    with (
        patch("sitesettings.mask_synced_secrets.copied_database_host", return_value="db"),
        pytest.raises(RuntimeError, match="not local"),
    ):
        mask_copied_production_secrets()
    site.refresh_from_db()
    assert site.telegram_bot_token == "123456:live"


def test_sync_from_vps_treats_only_loopback_as_local() -> None:
    """Скрипт восстановления не считает хост docker-сервиса «db» локальным."""
    script = ROOT / "scripts" / "sync-db-from-vps.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{script}"; '
            "hoocon_db_host_is_local 127.0.0.1 && hoocon_db_host_is_local localhost && "
            "hoocon_db_host_is_local ::1 && ! hoocon_db_host_is_local db && "
            "! hoocon_db_host_is_local 203.0.113.10",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_sync_from_vps_accepts_only_loopback_on_port_5432() -> None:
    """Порт туннеля не считается локальной базой, пока оператор явно не разрешил его."""
    script = ROOT / "scripts" / "sync-db-from-vps.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{script}"; '
            "hoocon_db_endpoint_is_safe 127.0.0.1 5432 0 && "
            "hoocon_db_endpoint_is_safe localhost 5432 0 && "
            "hoocon_db_endpoint_is_safe ::1 5432 0 && "
            "! hoocon_db_endpoint_is_safe 127.0.0.1 5555 0 && "
            "hoocon_db_endpoint_is_safe 127.0.0.1 5555 1 && "
            "! hoocon_db_endpoint_is_safe db 5432 0 && "
            "! hoocon_db_endpoint_is_safe 203.0.113.10 5432 1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_sync_from_vps_stops_before_ssh_on_a_tunnel_port(tmp_path: Path) -> None:
    """Скрипт с портом 5555 выходит до ssh и не начинает выгрузку."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "sync-db-from-vps.sh"
    target.write_text((ROOT / "scripts" / "sync-db-from-vps.sh").read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    (tmp_path / ".env").write_text(
        "DB_HOST=127.0.0.1\nDB_PORT=5555\nDB_NAME=hoocon\nDB_USER=hoocon\nDB_PASSWORD=secret\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text("#!/bin/sh\necho SSH_CALLED\nexit 99\n", encoding="utf-8")
    ssh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(tmp_path)}

    refused = subprocess.run(
        [str(target)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 1
    assert "5555" in refused.stderr
    assert "SSH_CALLED" not in refused.stdout

    allowed = subprocess.run(
        [str(target), "--allow-local-port"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 99
    assert "SSH_CALLED" in allowed.stdout


def test_backup_prune_keeps_newest_complete_copies(tmp_path: Path) -> None:
    """Уборка не стирает последние полные копии и не трогает незавершённый свежий каталог."""
    root = tmp_path / "backups"
    root.mkdir()

    def _dir(name: str, *, complete: bool, age_days: float) -> Path:
        path = root / name
        path.mkdir()
        if complete:
            (path / "COMPLETED").write_text(name, encoding="utf-8")
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    keep_a = _dir("a", complete=True, age_days=10)
    keep_b = _dir("b", complete=True, age_days=20)
    keep_c = _dir("c", complete=True, age_days=30)
    drop_old = _dir("d", complete=True, age_days=40)
    drop_partial = _dir("partial-old", complete=False, age_days=40)
    fresh = _dir("partial-new", complete=False, age_days=0)
    script = ROOT / "scripts" / "backup-retention.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{script}"; hoocon_prune_backups "{root}" 7 3',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert keep_a.is_dir() and keep_b.is_dir() and keep_c.is_dir()
    assert not drop_old.exists()
    assert not drop_partial.exists()
    assert fresh.is_dir()


@pytest.mark.django_db
def test_admin_message_poll_accepts_a_unicode_digit(client, django_user_model) -> None:
    """?after=² в опросе чата — пустой хвост, не 500."""
    from django.contrib.auth.models import Permission

    from supportchat.models import Channel, Conversation

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="after-superscript")
    staff = django_user_model.objects.create_user(
        username="chat-poll",
        password="test-pass-not-secret",
        is_staff=True,
    )
    staff.user_permissions.add(
        Permission.objects.get(codename="view_conversation", content_type__app_label="supportchat"),
    )
    client.force_login(staff)
    response = client.get(f"/admin/supportchat/conversation/{conv.pk}/messages/?after=²")
    assert response.status_code == 200
    assert response.json()["messages"] == []
