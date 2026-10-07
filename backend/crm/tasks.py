"""Celery tasks for CRM email: outbound send + inbound IMAP fetch."""

from __future__ import annotations

from typing import Any, cast

from celery import shared_task
from django.core.mail import EmailMessage as DjangoEmailMessage
from django.core.mail import EmailMultiAlternatives, get_connection

from config.logging_utils import setup_logger
from crm.email_body import html_email_to_plain, is_html_email_body
from crm.models import EmailMessage, EmailStatus

logger = setup_logger("hoocon.crm")


def _smtp_connection_for(msg: EmailMessage) -> Any | None:
    """Personal SMTP connection for outbound tied to a staff mailbox.

    У письма с ``mailbox`` (личный ящик менеджера) отправка идёт с его
    SMTP-кредов — ответ клиента придёт в тот же личный ящик. Пустой
    ``smtp_host``/логин/пароль или отсутствие ящика → None → дефолтный
    (общий env) backend.
    """
    mailbox = cast(Any, msg.mailbox)
    if mailbox is None:
        return None
    host = (mailbox.smtp_host or "").strip()
    username = (mailbox.imap_user or "").strip()
    password = getattr(mailbox, "imap_password_plain", None) or mailbox.imap_password or ""
    if not (host and username and password):
        return None
    return get_connection(
        host=host,
        port=mailbox.smtp_port,
        username=username,
        password=password,
        use_ssl=bool(mailbox.smtp_use_ssl),
        use_tls=not mailbox.smtp_use_ssl,
        fail_silently=False,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_crm_email(self: object, email_id: int) -> None:
    """Send a queued CRM EmailMessage via Django SMTP.

    Args:
        self: Celery task instance.
        email_id: EmailMessage primary key.

    Note:
        Logs only email_id and status — never full recipient PII.
    """
    try:
        msg = EmailMessage.objects.select_related("client", "mailbox").get(pk=email_id)
    except EmailMessage.DoesNotExist:
        logger.warning("crm_email_missing id=%s", email_id)
        return

    if msg.status == EmailStatus.SENT:
        return

    try:
        # Thread key: без него SMTP-сервер генерирует свой Message-ID и
        # входящий ответ (In-Reply-To) не свяжется с этой записью.
        if not msg.message_id:
            domain = (msg.from_email or "").split("@")[-1] or "hoocon.ru"
            msg.message_id = f"<crm-email-{msg.pk}@{domain}>"
            EmailMessage.objects.filter(pk=msg.pk, message_id__isnull=True).update(
                message_id=msg.message_id,
            )
        reply_to = (msg.reply_to_email or "").strip()
        connection = _smtp_connection_for(msg)
        # Личный ящик → From = адрес этого ящика (SMTP-сервер иначе
        # отклонит несовпадающий From); иначе — что записано при создании.
        mailbox = cast(Any, msg.mailbox)
        sender = (
            (mailbox.imap_user or "").strip() if mailbox is not None and connection is not None else ""
        ) or msg.from_email
        if sender != msg.from_email:
            msg.from_email = sender
            EmailMessage.objects.filter(pk=msg.pk).update(from_email=sender)
        django_msg: EmailMultiAlternatives | DjangoEmailMessage
        if is_html_email_body(msg.body):
            django_msg = EmailMultiAlternatives(
                subject=msg.subject,
                body=html_email_to_plain(msg.body),
                from_email=sender,
                to=[msg.to_email],
            )
            django_msg.attach_alternative(msg.body, "text/html")
        else:
            django_msg = DjangoEmailMessage(
                subject=msg.subject,
                body=msg.body,
                from_email=sender,
                to=[msg.to_email],
            )
        django_msg.extra_headers = {"Message-ID": msg.message_id}
        for att in msg.attachments.all():
            try:
                with att.file.open("rb") as fh:
                    django_msg.attach(
                        att.filename or "attachment",
                        fh.read(),
                        att.content_type or None,
                    )
            except OSError:
                logger.warning(
                    "crm_email_attachment_missing id=%s att=%s",
                    email_id,
                    att.pk,
                )
        if reply_to:
            django_msg.reply_to = [reply_to]
            # Lead «Ответить клиенту»: BCC manager so the thread starts in their
            # mailbox. Не нужно, когда отправка идёт с его же ящика — копия
            # и так в «Отправленных».
            if (
                msg.lead_id
                and reply_to.casefold() != (msg.to_email or "").strip().casefold()
                and reply_to.casefold() != sender.casefold()
            ):
                django_msg.bcc = [reply_to]
        if connection is not None:
            connection.send_messages([django_msg])
        else:
            django_msg.send(fail_silently=False)
    except Exception as exc:
        logger.exception("crm_email_send_failed id=%s", email_id)
        msg.mark_failed(f"{type(exc).__name__}")
        raise self.retry(exc=exc)  # type: ignore[attr-defined]

    msg.mark_sent()
    logger.info("crm_email_sent id=%s", email_id)


@shared_task(name="crm.fetch_inbound_email", bind=True, max_retries=2, default_retry_delay=120)
def fetch_inbound_email(self: object) -> str:
    """Poll IMAP for new inbound mail → EmailMessage(direction=inbound).

    Beat task (см. PeriodicTask ``crm.fetch_inbound_email``): общий ящик
    из env + личные ящики менеджеров (``accounts.StaffMailbox``). Когда
    источников нет — выходит сразу. Ошибка одного ящика не роняет цикл;
    здоровье каждого — в его ``last_error``.
    """
    from crm.imap_fetch import fetch_inbound_email as _fetch
    from crm.models import InboundMailboxState

    try:
        report = _fetch()
    except Exception as exc:
        state = InboundMailboxState.get_solo()
        state.last_error = type(exc).__name__[:300]
        state.save(update_fields=["last_error"])
        logger.exception("imap_fetch_failed")
        raise self.retry(exc=exc)  # type: ignore[attr-defined]
    if report.get("skipped"):
        return "disabled"
    return f"seen={report['seen']} created={report['created']} dup={report['duplicates']} err={report['errors']}"


@shared_task(name="crm.fetch_mango_recording", bind=True, max_retries=3, default_retry_delay=60)
def fetch_mango_recording(self: object, entry_id: str) -> str:
    """Download the Mango recording for a Call row into private media.

    Вызывается из webhook при ``recording_state=Completed``. Файл
    складывается в ``PRIVATE_MEDIA_ROOT/call_recordings/`` — скачивание
    только из админки (карточка звонка).
    """
    from crm.mango import download_recording
    from crm.models import Call

    try:
        call = Call.objects.get(entry_id=entry_id)
    except Call.DoesNotExist:
        logger.warning("mango_recording_no_call entry=%s", entry_id)
        return "no-call"
    if call.recording:
        return "already"
    recording_id = (call.recording_id or "").strip()
    if not recording_id:
        return "no-recording-id"

    try:
        payload = download_recording(recording_id)
    except Exception as exc:
        logger.exception("mango_recording_fetch_failed entry=%s", entry_id)
        raise self.retry(exc=exc)  # type: ignore[attr-defined]
    if not payload:
        return "empty"
    from django.core.files.base import ContentFile

    call.recording.save(f"{recording_id[:60]}.mp3", ContentFile(payload), save=True)
    logger.info("mango_recording_saved entry=%s bytes=%d", entry_id, len(payload))
    return "saved"
