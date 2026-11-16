"""IMAP fetch of inbound CRM mail (beat task ``crm.fetch_inbound_email``).

Яндекс 360 не отдаёт webhook — входящие забираем по IMAP (пароль
приложения в env, см. ``.env.example``). Каждое новое письмо →
``EmailMessage`` с привязкой:

- чужой отправитель: ``client`` по From; тред ``In-Reply-To`` /
  ``References`` или «Заявка #N» в теме — только если заявка этого же
  отправителя; новый отправитель без треда → заявка-консультация,
  и только если тема — заявка, консультация или запрос КП
  (режим ящика «Вся папка» забирает каждое письмо);
- наш адрес (логин открытого ящика, почта сотрудника, логин любого
  ящика менеджера): это не клиент и не новая заявка. «Кому» — клиент,
  ``In-Reply-To`` — его письмо. Копия ответа, пришедшая раньше письма
  клиента, ждёт без карточки и встаёт в ту же заявку, когда письмо
  клиента разбирается;
- вложения → ``EmailAttachment`` (private media, скачивание только staff).

Дедупликация: ``message_id`` (unique) + курсор ``last_uid`` в
``InboundMailboxState``. Письмо с битым From пропускается, курсор всё
равно двигается — poison message не зацикливает фетч.
"""

from __future__ import annotations

import base64
import email
import hashlib
import imaplib
import re
from dataclasses import dataclass
from datetime import UTC
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import InterfaceError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone

from config.logging_utils import setup_logger
from crm.email_body import email_body_for_reading, html_email_to_plain
from crm.mail_intake import MailIntake, subject_is_request
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


def encode_imap_utf7(name: str) -> str:
    """Encode a mailbox name for IMAP SELECT (RFC 3501 modified UTF-7).

    imaplib sends commands as ASCII. A Cyrillic folder such as «Заявки»
    raises UnicodeEncodeError unless it is encoded first. ASCII names,
    including INBOX, are left unchanged.
    """
    if name.isascii():
        return name
    out: list[str] = []
    chunk: list[str] = []

    def flush() -> None:
        if not chunk:
            return
        raw = "".join(chunk).encode("utf-16-be")
        token = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        out.append(f"&{token}-")
        chunk.clear()

    for char in name:
        if char == "&":
            flush()
            out.append("&-")
        elif " " <= char <= "~":
            flush()
            out.append(char)
        else:
            chunk.append(char)
    flush()
    return "".join(out)


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
                password=mb.imap_password_plain,
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
    # text/plain иногда сам является HTML (вставка из редактора) — в карточке тегов быть не должно.
    if plain:
        return email_body_for_reading(plain)[:_BODY_MAX_CHARS]
    if html:
        return html_email_to_plain(html)[:_BODY_MAX_CHARS]
    return ""


_MESSAGE_ID_MAX = 255


def normalize_message_id(raw: str | None) -> str | None:
    """Stored form of a Message-ID: as is, or ``sha256:<hex>`` past the column limit.

    A longer header used to fail the INSERT every run (and the cursor moved
    past it, so the mail was lost); hashing keeps dedupe and thread matching.
    """
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) <= _MESSAGE_ID_MAX:
        return value
    return "sha256:" + hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()


def _references(parsed: Message) -> set[str]:
    """Message-IDs this mail answers to (In-Reply-To + References)."""
    refs: set[str] = set()
    for header in ("In-Reply-To", "References"):
        for token in str(parsed.get(header) or "").split():
            token = token.strip()
            if token.startswith("<") and token.endswith(">"):
                refs.add(cast(str, normalize_message_id(token)))
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


def _sender(parsed: Message) -> tuple[str, str]:
    """Normalized From and display name.

    Raises:
        ValueError: письмо без валидного From — пропускаем.
    """
    from crm.services import normalize_client_email, normalize_client_name

    from_raw = _decode_header_value(str(parsed.get("From") or ""))
    display_name, address = parseaddr(from_raw)
    normalized = normalize_client_email(address)
    if not normalized:
        raise ValueError("inbound mail without From address")
    return normalized, normalize_client_name(display_name)


def _header_addresses(parsed: Message, header: str) -> list[str]:
    """Normalized addresses from one header, order kept, duplicates dropped."""
    from crm.services import normalize_client_email

    raw = _decode_header_value(str(parsed.get(header) or ""))
    found: list[str] = []
    for _name, address in getaddresses([raw]):
        normalized = normalize_client_email(address)
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def _known_staff_addresses(box: _Mailbox) -> set[str]:
    """Logins and staff emails. A letter from these addresses is ours, not a customer."""
    from django.contrib.auth import get_user_model

    from accounts.models import StaffMailbox
    from crm.services import normalize_client_email

    found: set[str] = set()
    user_model = get_user_model()
    staff_emails = user_model.objects.filter(is_staff=True).values_list("email", flat=True)
    mailbox_logins = StaffMailbox.objects.exclude(imap_user="").values_list("imap_user", flat=True)
    candidates = [*staff_emails, *mailbox_logins, box.user, getattr(settings, "IMAP_USER", "") or ""]
    for raw in candidates:
        normalized = normalize_client_email(raw)
        if normalized:
            found.add(normalized)
    return found


def _counterparty(addresses: list[str], staff: set[str]) -> str:
    """First address that is not ours — the client on a manager's copy."""
    for address in addresses:
        if address not in staff:
            return address
    return ""


def _immediate_reply_id(parsed: Message) -> str:
    """In-Reply-To, or the last References id (RFC 5322 immediate parent)."""
    direct = normalize_message_id(parsed.get("In-Reply-To")) or ""
    if direct:
        return direct
    last = ""
    for token in str(parsed.get("References") or "").split():
        normalized = normalize_message_id(token.strip())
        if normalized:
            last = normalized
    return last


def _parent_message(references: set[str]) -> EmailMessage | None:
    """Stored message this one answers. Prefer a row that already has a lead."""
    if not references:
        return None
    rows = list(EmailMessage.objects.filter(message_id__in=references).select_related("lead", "client"))
    for row in rows:
        if row.lead_id:
            return row
    return rows[0] if rows else None


def _existing_client(addresses: list[str], staff: set[str]) -> Client | None:
    """Client card for an address already in CRM. Does not create one."""
    external = [address for address in addresses if address not in staff]
    if not external:
        return None
    found = {client.email: client for client in Client.objects.filter(email__in=external)}
    for address in external:
        if address in found:
            return found[address]
    return None


def _our_reply_target(
    *,
    sender: str,
    box: _Mailbox,
    staff: set[str],
    references: set[str],
    to_addresses: list[str],
) -> tuple[Client | None, Lead | None]:
    """Client and lead for a letter sent from our side.

    From the mailbox we just opened, In-Reply-To is enough: the copy sits
    in that account. From another known manager address, attach only when
    «кому» is the lead's contact — a bare message-id must not join a
    foreign thread.
    """
    from crm.services import normalize_client_email

    parent = _parent_message(references)
    client = _existing_client(to_addresses, staff)
    lead: Lead | None = None
    if parent is not None:
        if parent.client_id:
            client = cast(Client, parent.client)
        if parent.lead_id:
            lead = cast(Lead, parent.lead)
            if client is None and lead.client_id:
                client = cast(Client, lead.client)
    if lead is None:
        return client, None
    if sender == normalize_client_email(box.user):
        return client, lead
    lead_email = normalize_client_email(lead.email)
    if lead_email and lead_email in to_addresses:
        return client, lead
    return client, None


def _record_mail_activity(*, client: Client, lead: Lead | None, subject: str, body: str) -> None:
    """One timeline row for a stored letter."""
    Activity.objects.create(
        client=client,
        lead=lead,
        activity_type=ActivityType.EMAIL,
        subject=subject,
        body=body[:2000],
    )


def _attach_pending_replies(
    *,
    message_id: str | None,
    client: Client,
    lead: Lead | None,
    staff: set[str],
) -> None:
    """Hang waiting manager copies on the customer letter they answer."""
    from crm.services import normalize_client_email

    if not message_id:
        return
    pending = EmailMessage.objects.filter(
        in_reply_to=message_id,
        lead__isnull=True,
        from_email__in=staff,
    )
    lead_email = normalize_client_email(lead.email) if lead is not None else ""
    for row in pending:
        to_addr = normalize_client_email(row.to_email)
        addressed_elsewhere = bool(to_addr) and to_addr not in staff and to_addr != lead_email
        if lead is not None and addressed_elsewhere:
            continue
        had_client = row.client_id is not None
        had_lead = row.lead_id is not None
        row.client = client
        if lead is not None:
            row.lead = lead
        row.save(update_fields=["client", "lead"])
        if lead is not None and not had_lead and had_client:
            waiting = (
                Activity.objects.filter(
                    client_id=client.pk,
                    lead__isnull=True,
                    activity_type=ActivityType.EMAIL,
                    subject=row.subject,
                )
                .order_by("-id")
                .first()
            )
            if waiting is not None:
                waiting.lead = lead
                waiting.save(update_fields=["lead"])
                continue
        if not had_client or (lead is not None and not had_lead):
            _record_mail_activity(client=client, lead=lead, subject=row.subject, body=row.body)


def _resolve_client(parsed: Message) -> tuple[Client, bool]:
    """Client by From address (create with display-name for unknown senders).

    Raises:
        ValueError: письмо без валидного From — пропускаем.
    """
    sender, display_name = _sender(parsed)
    client = Client.objects.filter(email=sender).first()
    if client is not None:
        return client, False
    client = Client.objects.create(
        email=sender,
        name=(display_name or sender)[:200],
        company=_company_from_sender_email(sender),
    )
    return client, True


def _find_lead(*, references: set[str], subject: str, client: Client) -> Lead | None:
    """Thread match (In-Reply-To → outbound message_id), then «Заявка #N».

    Both keys come from the sender (a subject is free text, old Message-IDs
    leak in forwards), so a lead is matched only when it belongs to the
    same sender — otherwise anyone could post into a foreign lead.
    """
    owned = Lead.objects.filter(Q(client=client) | Q(email__iexact=client.email))
    if references:
        parent = (
            EmailMessage.objects.filter(
                message_id__in=references,
                lead__in=owned,
            )
            .select_related("lead")
            .first()
        )
        if parent is not None and parent.lead_id:
            return cast(Lead, parent.lead)
    match = _LEAD_REF_RE.search(subject or "")
    if match:
        return owned.filter(pk=int(match.group(1))).first()
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
    """Route an email-created lead.

    A personal mailbox keeps the lead: the letter arrived for that manager.
    The shared mailbox leaves it unassigned, same as a form on the site.
    The sales letter then offers «Взять».
    """
    from leads.services import assign_lead_to_user

    if box.staff_mailbox is not None:
        assign_lead_to_user(lead, box.staff_mailbox.user)
        return
    from django.db import transaction

    from leads.tasks import send_lead_notification

    lead_id = lead.pk

    def _notify_sales() -> None:
        send_lead_notification.delay(lead_id)

    transaction.on_commit(_notify_sales)


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
    timeout = settings.IMAP_TIMEOUT
    if settings.IMAP_USE_SSL:
        conn = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT, timeout=timeout)
    else:
        conn = imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT, timeout=timeout)
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
        raise imaplib.IMAP4.error(f"UID FETCH failed: {typ}")
    for item in data or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    raise ValueError("UID FETCH returned no message body")


def _store_our_copy(
    *,
    parsed: Message,
    uid: int,
    box: _Mailbox,
    staff: set[str],
    sender: str,
    subject: str,
    body: str,
    references: set[str],
    message_id: str | None,
) -> None:
    """Manager's own letter: outbound to the client, never a new lead."""
    to_addresses = _header_addresses(parsed, "To")
    client, lead = _our_reply_target(
        sender=sender,
        box=box,
        staff=staff,
        references=references,
        to_addresses=to_addresses,
    )
    external = _counterparty(to_addresses, staff)
    to_email = external or (to_addresses[0] if to_addresses else box.user)
    received = _received_at(parsed)
    outgoing = bool(external)
    with transaction.atomic():
        row = EmailMessage.objects.create(
            client=client,
            lead=lead,
            direction=EmailDirection.OUTBOUND if outgoing else EmailDirection.INBOUND,
            status=EmailStatus.SENT if outgoing else EmailStatus.RECEIVED,
            to_email=to_email[:254],
            from_email=sender,
            subject=subject,
            body=body[:_BODY_MAX_CHARS],
            message_id=message_id,
            in_reply_to=_immediate_reply_id(parsed),
            imap_uid=uid,
            mailbox=box.staff_mailbox,
            received_at=received,
            sent_at=received if outgoing else None,
        )
        _save_attachments(parsed, row)
        if client is not None:
            _record_mail_activity(client=client, lead=lead, subject=subject, body=body)


def _store_customer_mail(
    *,
    parsed: Message,
    uid: int,
    box: _Mailbox,
    staff: set[str],
    subject: str,
    body: str,
    references: set[str],
    message_id: str | None,
) -> EmailMessage:
    """Inbound letter from a customer. A new sender without a thread opens a lead."""
    with transaction.atomic():
        client, is_new_client = _resolve_client(parsed)
        lead = _find_lead(references=references, subject=subject, client=client)
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
            in_reply_to=_immediate_reply_id(parsed),
            imap_uid=uid,
            mailbox=box.staff_mailbox,
            received_at=_received_at(parsed),
        )
        _save_attachments(parsed, msg_row)
        _record_mail_activity(client=client, lead=lead, subject=subject, body=body)
        _attach_pending_replies(message_id=message_id, client=client, lead=lead, staff=staff)
    return msg_row


def _store_raw(raw: bytes, uid: int, box: _Mailbox, staff: set[str]) -> str:
    """Store one already-fetched message; 'created' | 'duplicate'."""
    parsed = email.message_from_bytes(raw)
    message_id = normalize_message_id(parsed.get("Message-ID"))
    if message_id and EmailMessage.objects.filter(message_id=message_id).exists():
        return "duplicate"

    sender, _display_name = _sender(parsed)
    subject = _decode_header_value(str(parsed.get("Subject") or ""))[:300]
    body = _extract_body(parsed)
    references = _references(parsed)
    if sender in staff:
        _store_our_copy(
            parsed=parsed,
            uid=uid,
            box=box,
            staff=staff,
            sender=sender,
            subject=subject,
            body=body,
            references=references,
            message_id=message_id,
        )
        return "created"

    msg_row = _store_customer_mail(
        parsed=parsed,
        uid=uid,
        box=box,
        staff=staff,
        subject=subject,
        body=body,
        references=references,
        message_id=message_id,
    )
    _notify_staff(msg_row, box)
    return "created"


# Network / server / DB hiccups: retry the same UID next run instead of
# skipping it. Anything else is a broken message and is passed over.
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    imaplib.IMAP4.error,
    OSError,
    OperationalError,
    InterfaceError,
)
_TRANSIENT_RETRIES = 3


def _transient_budget_spent(box: _Mailbox, uid: int) -> bool:
    """Count a transient failure; True once a UID failed ``_TRANSIENT_RETRIES`` runs."""
    key = f"imap_fetch:transient:{box.key}:{uid}"
    cache.add(key, 0, timeout=86400)
    try:
        failures = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=86400)
        failures = 1
    return failures >= _TRANSIENT_RETRIES


def _take_uid(conn: imaplib.IMAP4, uid: int, box: _Mailbox, report: dict[str, int]) -> bytes | None:
    """Fetch one UID. None — skipped (poison or retries spent). Raises to retry later."""
    try:
        return _fetch_raw(conn, uid)
    except _TRANSIENT_ERRORS as exc:
        logger.warning("imap_fetch_transient box=%s uid=%s: %s", box.key, uid, exc)
        report["errors"] += 1
        if not _transient_budget_spent(box, uid):
            raise
        logger.error("imap_fetch_giving_up box=%s uid=%s", box.key, uid)
    except Exception:  # noqa: BLE001 — «ядовитое» письмо: пропускаем
        logger.exception("imap_fetch_message_failed box=%s uid=%s", box.key, uid)
        report["errors"] += 1
    return None


@dataclass
class _Incoming:
    """One fetched letter, before we decide whether CRM wants it."""

    uid: int
    raw: bytes
    sender: str
    subject: str
    references: set[str]
    message_id: str | None


def _leads_named_in_subjects(items: list[_Incoming], staff: set[str]) -> set[tuple[int, str]]:
    """(lead pk, sender) when «Заявка #N» belongs to that sender."""
    from crm.services import normalize_client_email

    wanted: dict[int, list[str]] = {}
    for item in items:
        if item.sender in staff:
            continue
        match = _LEAD_REF_RE.search(item.subject or "")
        if match:
            wanted.setdefault(int(match.group(1)), []).append(item.sender)
    if not wanted:
        return set()
    rows = Lead.objects.filter(pk__in=wanted).values_list("pk", "email", "client__email")
    allowed: set[tuple[int, str]] = set()
    for pk, lead_email, client_email in rows:
        owners = {normalize_client_email(lead_email or ""), normalize_client_email(client_email or "")}
        owners.discard("")
        for sender in wanted.get(pk, []):
            if sender in owners:
                allowed.add((pk, sender))
    return allowed


def _related_uids(items: list[_Incoming], box: _Mailbox, staff: set[str]) -> set[int]:
    """UIDs to import. The rest of the folder stays in the mailbox."""
    intake = getattr(box.state, "intake", MailIntake.REQUESTS) or MailIntake.REQUESTS
    if intake == MailIntake.ALL:
        return {item.uid for item in items}
    needles = getattr(box.state, "intake_subjects", "") or ""
    known: set[str] = set()
    every_ref: set[str] = set()
    for item in items:
        every_ref.update(item.references)
    if every_ref:
        stored_ids = EmailMessage.objects.filter(message_id__in=every_ref).values_list("message_id", flat=True)
        known.update(message_id for message_id in stored_ids if message_id)
    named = _leads_named_in_subjects(items, staff)
    related: set[int] = set()
    related_ids: set[str] = set()

    def _is_related(item: _Incoming) -> bool:
        if item.references & known or item.references & related_ids:
            return True
        if item.sender not in staff:
            match = _LEAD_REF_RE.search(item.subject or "")
            if match and (int(match.group(1)), item.sender) in named:
                return True
        if intake == MailIntake.THREADS:
            return False
        return subject_is_request(item.subject, needles)

    changed = True
    while changed:
        changed = False
        for item in items:
            if item.uid in related or not _is_related(item):
                continue
            related.add(item.uid)
            if item.message_id:
                related_ids.add(item.message_id)
            changed = True
    return related


def _cursor_after(last_uid: int, seen: list[int], handled: set[int], stop_before: int | None) -> int:
    """Highest UID this run may pass.

    The cursor stops before the first UID that still needs a retry, even
    when a higher UID was stored already — the next run dedups that one.
    """
    advanced = last_uid
    for uid in sorted(seen):
        if stop_before is not None and uid >= stop_before:
            break
        if uid not in handled:
            break
        advanced = uid
    return advanced


def _fetch_box(box: _Mailbox, limit: int, report: dict[str, int]) -> None:
    """Fetch one mailbox; merge counters; update cursor + health on its row.

    Customer letters are stored before our own copies from the same batch,
    so a reply that landed in the folder first still joins the client's lead.
    """
    state = box.state
    staff = _known_staff_addresses(box)
    conn = _connect(box)
    try:
        conn.select(encode_imap_utf7(box.folder), readonly=True)
        uids = _new_uids(conn, state.last_uid, limit)
        report["seen"] += len(uids)
        last_error = ""
        stop_before: int | None = None
        skipped: set[int] = set()
        incoming: list[_Incoming] = []
        for uid in uids:
            try:
                raw = _take_uid(conn, uid, box, report)
            except _TRANSIENT_ERRORS as exc:
                last_error = f"UID {uid}: {exc}"[:500]
                stop_before = uid
                break
            if raw is None:
                skipped.add(uid)
                continue
            try:
                parsed = email.message_from_bytes(raw)
                sender, _display_name = _sender(parsed)
            except Exception:  # noqa: BLE001 — битый From: пропускаем
                logger.exception("imap_fetch_message_failed box=%s uid=%s", box.key, uid)
                report["errors"] += 1
                skipped.add(uid)
                continue
            incoming.append(
                _Incoming(
                    uid=uid,
                    raw=raw,
                    sender=sender,
                    subject=_decode_header_value(str(parsed.get("Subject") or ""))[:300],
                    references=_references(parsed),
                    message_id=normalize_message_id(parsed.get("Message-ID")),
                ),
            )
        keep = _related_uids(incoming, box, staff)
        customers: list[tuple[int, bytes]] = []
        ours: list[tuple[int, bytes]] = []
        for item in incoming:
            if item.uid not in keep:
                logger.info("imap_fetch_skip_unrelated box=%s uid=%s", box.key, item.uid)
                skipped.add(item.uid)
                continue
            (ours if item.sender in staff else customers).append((item.uid, item.raw))

        handled = set(skipped)
        for uid, raw in [*customers, *ours]:
            try:
                result = _store_raw(raw, uid, box, staff)
            except _TRANSIENT_ERRORS as exc:
                logger.warning("imap_fetch_transient box=%s uid=%s: %s", box.key, uid, exc)
                report["errors"] += 1
                if not _transient_budget_spent(box, uid):
                    last_error = f"UID {uid}: {exc}"[:500]
                    stop_before = uid
                    break
                logger.error("imap_fetch_giving_up box=%s uid=%s", box.key, uid)
                handled.add(uid)
            except Exception:  # noqa: BLE001 — «ядовитое» письмо: пропускаем
                logger.exception("imap_fetch_message_failed box=%s uid=%s", box.key, uid)
                report["errors"] += 1
                handled.add(uid)
            else:
                report["created" if result == "created" else "duplicates"] += 1
                handled.add(uid)

        seen = sorted({*skipped, *(uid for uid, _raw in customers), *(uid for uid, _raw in ours)})
        state.last_uid = _cursor_after(state.last_uid, seen, handled, stop_before)
        state.last_run_at = timezone.now()
        state.last_error = last_error
        state.save(update_fields=["last_uid", "last_run_at", "last_error"])
    finally:
        _logout(conn)


def fetch_inbound_email(*, limit: int | None = None) -> dict[str, int]:
    """Poll every configured mailbox and store new mail.

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
