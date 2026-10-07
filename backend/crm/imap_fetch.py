"""IMAP fetch of inbound CRM mail (beat task ``crm.fetch_inbound_email``).

Яндекс 360 не отдаёт webhook — входящие забираем по IMAP (пароль
приложения в env, см. ``.env.example``). Каждое новое письмо →
``EmailMessage(direction=inbound, status=received)`` с привязкой:

- ``client`` — по адресу отправителя (``get_or_create`` по email);
- ``lead`` — тред ``In-Reply-To``/``References`` → ``message_id``
  исходящего, либо «Заявка #N» в теме; для **нового** отправителя без
  треда — новая заявка-консультация (чтобы письмо не потерялось в inbox);
- вложения → ``EmailAttachment`` (private media, скачивание только staff).

Дедупликация: ``message_id`` (unique) + курсор ``last_uid`` в
``InboundMailboxState``. Письмо с битым From пропускается, курсор всё
равно двигается — poison message не зацикливает фетч.
"""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import UTC
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, cast

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from config.logging_utils import setup_logger
from crm.email_body import html_email_to_plain
from crm.models import (
    Activity,
    ActivityType,
    Client,
    EmailAttachment,
    EmailDirection,
    EmailMessage,
    EmailStatus,
    InboundMailboxState,
)
from leads.models import Lead

logger = setup_logger("hoocon.crm")

# «Re: Заявка #123», «lead 45», «заявку №12» → lead pk.
_LEAD_REF_RE = re.compile(r"(?:заявк\w*|lead)\s*[#№]?\s*(\d+)", re.IGNORECASE)

_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024
_ATTACHMENT_MAX_COUNT = 20
_BODY_MAX_CHARS = 20000
_LEAD_MESSAGE_MAX_CHARS = 4000

# Бесплатные почтовые домены — по ним компанию не угадываем: домен
# не про работодателя отправителя.
_FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yandex.ru",
        "ya.ru",
        "yandex.com",
        "yandex.kz",
        "yandex.by",
        "narod.ru",
        "mail.ru",
        "bk.ru",
        "inbox.ru",
        "list.ru",
        "internet.ru",
        "rambler.ru",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "yahoo.com",
        "yahoo.ru",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "mail.com",
        "gmx.com",
        "gmx.net",
        "ukr.net",
        "tut.by",
        "mail.by",
        "list.am",
    }
)

# Служебные поддомены почтового хостинга — обрезаем при угадывании.
_MAIL_SERVICE_SUBDOMAINS = frozenset({"mail", "webmail", "smtp", "pop", "pop3", "imap", "mx", "mx1", "mx2"})


@dataclass
class _Mailbox:
    """One fetch source: общий env-ящик или личный ящик менеджера."""

    key: str  # "env" | "staff:<pk>" — для логов
    user: str  # IMAP login / адрес ящика
    password: str
    folder: str
    state: Any  # InboundMailboxState | StaffMailbox — курсор + last_error
    staff_mailbox: Any | None = None  # accounts.StaffMailbox → EmailMessage.mailbox


def _mailboxes() -> list[_Mailbox]:
    """Configured sources: общий ящик из env + личные ящики staff."""
    from accounts.models import StaffMailbox

    boxes: list[_Mailbox] = []
    if getattr(settings, "IMAP_ENABLED", False) and settings.IMAP_USER and settings.IMAP_PASSWORD:
        state = InboundMailboxState.get_solo()
        boxes.append(
            _Mailbox(
                key="env",
                user=settings.IMAP_USER,
                password=settings.IMAP_PASSWORD,
                folder=(state.folder or settings.IMAP_FOLDER) or "INBOX",
                state=state,
            ),
        )
    staff_boxes = (
        StaffMailbox.objects.filter(is_enabled=True)
        .exclude(imap_user="")
        .exclude(imap_password="")
        .select_related("user")
    )
    for mb in staff_boxes:
        boxes.append(
            _Mailbox(
                key=f"staff:{mb.pk}",
                user=mb.imap_user,
                password=mb.imap_password,
                folder=mb.folder or "INBOX",
                state=mb,
                staff_mailbox=mb,
            ),
        )
    return boxes


def _decode_header_value(raw: str | None) -> str:
    """Decode RFC-2047 header to str; empty on failure."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001 — битые заголовки не должны ронять fetch
        return raw if isinstance(raw, str) else ""


def _payload_text(part: Message) -> str:
    """Decode a MIME part payload to text (charset-aware, lossy)."""
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_body(parsed: Message) -> str:
    """Prefer text/plain; fallback text/html → plain (existing helper)."""
    plain = ""
    html = ""
    for part in parsed.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = str(part.get("Content-Disposition") or "")
        if "attachment" in disposition.lower():
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain" and not plain:
            plain = _payload_text(part)
        elif content_type == "text/html" and not html:
            html = _payload_text(part)
    if plain:
        return plain[:_BODY_MAX_CHARS]
    if html:
        return html_email_to_plain(html)[:_BODY_MAX_CHARS]
    return ""


def _references(parsed: Message) -> set[str]:
    """Message-IDs this mail answers to (In-Reply-To + References)."""
    refs: set[str] = set()
    for header in ("In-Reply-To", "References"):
        for token in str(parsed.get(header) or "").split():
            token = token.strip()
            if token.startswith("<") and token.endswith(">"):
                refs.add(token)
    return refs


def _received_at(parsed: Message) -> Any:
    """Parse the Date header; None on garbage."""
    try:
        dt = parsedate_to_datetime(str(parsed.get("Date") or ""))
    except (TypeError, ValueError):
        return None
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, UTC)
    return dt


def _company_from_sender_email(email_addr: str) -> str:
    """Company label guess from a corporate email domain.

    buyer@romashka.ru → «romashka.ru»: карточка не пустая, менеджер
    при необходимости правит юрлицо руками, а owner-правила
    (``Client.company_key`` / ``CompanyManagerRule``) могут матчить
    уже сейчас. Для бесплатных доменов (gmail, yandex, …) — пусто:
    там домен не про компанию.
    """
    domain = email_addr.rpartition("@")[2].strip().lower()
    if not domain or domain in _FREE_MAIL_DOMAINS:
        return ""
    labels = domain.split(".")
    if len(labels) > 2 and labels[0] in _MAIL_SERVICE_SUBDOMAINS:
        domain = ".".join(labels[1:])
    if domain in _FREE_MAIL_DOMAINS:
        return ""
    return domain[:200]


def _resolve_client(parsed: Message) -> tuple[Client, bool]:
    """Client by From address (create with display-name for unknown senders).

    Raises:
        ValueError: письмо без валидного From — пропускаем.
    """
    from crm.services import normalize_client_email, normalize_client_name

    from_raw = _decode_header_value(str(parsed.get("From") or ""))
    display_name, address = parseaddr(from_raw)
    normalized = normalize_client_email(address)
    if not normalized:
        raise ValueError("inbound mail without From address")
    client = Client.objects.filter(email=normalized).first()
    if client is not None:
        return client, False
    name = normalize_client_name(display_name) or normalized
    client = Client.objects.create(
        email=normalized,
        name=name[:200],
        company=_company_from_sender_email(normalized),
    )
    return client, True


def _find_lead(*, references: set[str], subject: str) -> Lead | None:
    """Thread match (In-Reply-To → outbound message_id), then «Заявка #N»."""
    if references:
        parent = (
            EmailMessage.objects.filter(
                message_id__in=references,
                lead__isnull=False,
            )
            .select_related("lead")
            .first()
        )
        if parent is not None and parent.lead_id:
            return cast(Lead, parent.lead)
    match = _LEAD_REF_RE.search(subject or "")
    if match:
        return Lead.objects.filter(pk=int(match.group(1))).first()
    return None


def _create_lead_from_email(*, client: Client, subject: str, body: str) -> Lead:
    """Consultation lead for a first-time sender without a thread match.

    Нужен, чтобы новое входящее письмо не осталось «только в Письмах» —
    попадает в общий inbox заявок менеджера.
    """
    return Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name=client.name or client.email,
        email=client.email,
        company=client.company or "",
        message=f"{subject}\n\n{body[:_LEAD_MESSAGE_MAX_CHARS]}".strip(),
    )


def _route_new_lead(box: _Mailbox, lead: Lead) -> None:
    """Assign owner to an email-created lead via the canonical pipeline.

    Личный ящик → его владелец (письмо пришло лично ему). Общий ящик →
    ``assign_lead_on_create``: pinned-правила компаний (Admin) →
    закреплённый владелец по ``company_key`` → round-robin по группе
    «Менеджер» с курсором ``SiteSettings`` и гейтом ``lead_routing_mode``.
    Оба пути закрепляют ``Client.assignee``, если он пуст.
    """
    from leads.services import assign_lead_on_create, assign_lead_to_user

    if box.staff_mailbox is not None:
        assign_lead_to_user(lead, box.staff_mailbox.user)
    else:
        assign_lead_on_create(lead)


def _save_attachments(parsed: Message, msg_row: EmailMessage) -> int:
    """Persist attachments into private media; count saved."""
    saved = 0
    for part in parsed.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        disposition = str(part.get("Content-Disposition") or "")
        if filename is None and "attachment" not in disposition.lower():
            continue
        if saved >= _ATTACHMENT_MAX_COUNT:
            break
        payload = part.get_payload(decode=True) or b""
        if not payload or len(payload) > _ATTACHMENT_MAX_BYTES:
            continue
        fname = (_decode_header_value(filename) or "attachment.bin")[:255]
        attachment = EmailAttachment(
            email=msg_row,
            filename=fname,
            content_type=part.get_content_type(),
            size=len(payload),
        )
        attachment.file.save(fname, ContentFile(payload), save=True)
        saved += 1
    return saved


def _notify_staff(msg_row: EmailMessage, box: _Mailbox) -> None:
    """Telegram alert on inbound mail; failures never break the fetch.

    Письмо в личный ящик → алерт только его владельцу; общий ящик →
    всем менеджерам, как раньше.
    """
    try:
        from accounts.telegram_alerts import (
            format_staff_telegram_message,
            send_telegram_to_users,
            staff_telegram_recipients_managers,
        )

        url = f"/admin/crm/emailmessage/{msg_row.pk}/change/"
        text = format_staff_telegram_message(
            title="Входящее письмо",
            body=f"{msg_row.from_email} — {msg_row.subject[:200]}",
            url=url,
        )
        if box.staff_mailbox is not None:
            send_telegram_to_users([box.staff_mailbox.user], text)
        else:
            send_telegram_to_users(staff_telegram_recipients_managers(), text)
    except Exception:  # noqa: BLE001 — алерт не должен ронять fetch
        logger.exception("imap_notify_failed id=%s", msg_row.pk)


def _connect(box: _Mailbox) -> imaplib.IMAP4:
    """Login to IMAP for one mailbox (host/port/SSL — общие из settings)."""
    conn: imaplib.IMAP4
    if settings.IMAP_USE_SSL:
        conn = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
    else:
        conn = imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT)
    conn.login(box.user, box.password)
    return conn


def _logout(conn: imaplib.IMAP4) -> None:
    """Best-effort logout."""
    try:
        conn.logout()
    except Exception:  # noqa: BLE001
        pass


def _new_uids(conn: imaplib.IMAP4, last_uid: int, limit: int) -> list[int]:
    """UIDs strictly above cursor, sorted, capped at limit."""
    start = last_uid + 1
    typ, data = conn.uid("search", "UID", f"{start}:*")
    if typ != "OK" or not data or not data[0]:
        return []
    # IMAP returns the last message even when no UID matches — refilter.
    uids = sorted(u for u in (int(token) for token in data[0].split() if token.isdigit()) if u >= start)
    return uids[:limit]


def _fetch_raw(conn: imaplib.IMAP4, uid: int) -> bytes:
    """UID FETCH (RFC822) → raw bytes."""
    typ, data = conn.uid("fetch", str(uid), "(RFC822)")
    if typ != "OK":
        raise ValueError(f"UID FETCH failed: {typ}")
    for item in data or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    raise ValueError("UID FETCH returned no message body")


def _process_uid(conn: imaplib.IMAP4, uid: int, box: _Mailbox) -> str:
    """Fetch + store one message; 'created' | 'duplicate'."""
    raw = _fetch_raw(conn, uid)
    parsed = email.message_from_bytes(raw)
    message_id = (parsed.get("Message-ID") or "").strip() or None
    if message_id and EmailMessage.objects.filter(message_id=message_id).exists():
        return "duplicate"

    subject = _decode_header_value(str(parsed.get("Subject") or ""))[:300]
    body = _extract_body(parsed)
    references = _references(parsed)

    with transaction.atomic():
        client, is_new_client = _resolve_client(parsed)
        lead = _find_lead(references=references, subject=subject)
        if lead is None and is_new_client:
            lead = _create_lead_from_email(client=client, subject=subject, body=body)
            _route_new_lead(box, lead)
        msg_row = EmailMessage.objects.create(
            client=client,
            lead=lead,
            direction=EmailDirection.INBOUND,
            status=EmailStatus.RECEIVED,
            to_email=box.user,
            from_email=client.email,
            subject=subject,
            body=body[:_BODY_MAX_CHARS],
            message_id=message_id,
            in_reply_to=(parsed.get("In-Reply-To") or "").strip()[:255],
            imap_uid=uid,
            mailbox=box.staff_mailbox,
            received_at=_received_at(parsed),
        )
        _save_attachments(parsed, msg_row)
        Activity.objects.create(
            client=client,
            lead=lead,
            activity_type=ActivityType.EMAIL,
            subject=subject,
            body=body[:2000],
        )
    _notify_staff(msg_row, box)
    return "created"


def _fetch_box(box: _Mailbox, limit: int, report: dict[str, int]) -> None:
    """Fetch one mailbox; merge counters; update cursor + health on its row."""
    state = box.state
    conn = _connect(box)
    try:
        conn.select(box.folder, readonly=True)
        uids = _new_uids(conn, state.last_uid, limit)
        report["seen"] += len(uids)
        max_uid = state.last_uid
        for uid in uids:
            try:
                result = _process_uid(conn, uid, box)
            except Exception:  # noqa: BLE001 — считаем и идём дальше
                logger.exception("imap_fetch_message_failed box=%s uid=%s", box.key, uid)
                report["errors"] += 1
            else:
                report["created" if result == "created" else "duplicates"] += 1
            max_uid = max(max_uid, uid)
        state.last_uid = max_uid
        state.last_run_at = timezone.now()
        state.last_error = ""
        state.save(update_fields=["last_uid", "last_run_at", "last_error"])
    finally:
        _logout(conn)


def fetch_inbound_email(*, limit: int | None = None) -> dict[str, int]:
    """Poll every configured mailbox; store new mail as inbound EmailMessage.

    Источники: общий ящик из env (IMAP_ENABLED) + включённые личные
    ящики менеджеров (``accounts.StaffMailbox``). Ящик с ошибкой логина
    не роняет остальные — ошибка пишется в его ``last_error``.

    Args:
        limit: max messages per mailbox per run (default
            ``settings.IMAP_FETCH_LIMIT``).

    Returns:
        Counters: ``seen`` uids checked, ``created``, ``duplicates``,
        ``errors``; ``{"skipped": 1}`` when no sources configured.
    """
    boxes = _mailboxes()
    if not boxes:
        return {"skipped": 1}
    report = {"seen": 0, "created": 0, "duplicates": 0, "errors": 0}
    for box in boxes:
        try:
            _fetch_box(box, limit or settings.IMAP_FETCH_LIMIT, report)
        except Exception as exc:  # noqa: BLE001 — один ящик не роняет цикл
            logger.exception("imap_fetch_box_failed box=%s", box.key)
            box.state.last_error = type(exc).__name__[:300]
            box.state.save(update_fields=["last_error"])
            report["errors"] += 1
    logger.info(
        "imap_fetch_done boxes=%s seen=%s created=%s dup=%s err=%s",
        len(boxes),
        report["seen"],
        report["created"],
        report["duplicates"],
        report["errors"],
    )
    return report
