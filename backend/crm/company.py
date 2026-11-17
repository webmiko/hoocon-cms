"""Company card helpers: auto-link from Client, colleagues, merge."""

from __future__ import annotations

import re
from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from config.logging_utils import setup_logger
from crm.models import Client, Company, CompanyMember

logger = setup_logger("hoocon.crm")

MISSING_COMPANY_NOTE = "Автозаметка: компания не найдена в заявках и подписи письма — уточнить у контакта."

# «ООО "Хогон"» встречается в цитируемых письмах наших менеджеров —
# не компания клиента.
_OWN_COMPANY_KEYS = {"хогон", "ооо хогон", "hoocon"}

_ORG_FORM_PATTERN = r"ООО|АО|ПАО|ЗАО|ОАО|НАО|АНО|НКО|ГУП|МУП|ФГУП|ИП"
# Граница слева: заглавная буква перед формой = часть другого слова
# («СИП Иванов» — марка кабеля, не «ИП Иванов»).
_QUOTED_ORG_RE = re.compile(
    rf"(?<![А-ЯЁA-Z])(?P<form>{_ORG_FORM_PATTERN})\s*[«\"'„“”]\s*"
    rf"(?P<name>[^«»\"'„“”\n]{{2,80}}?)\s*[»\"'„“”]",
)
_STANDALONE_ORG_RE = re.compile(
    rf"^\s*(?P<form>{_ORG_FORM_PATTERN})\s+"
    rf"(?P<name>[«\"'„“”]?[\w][\w.\-]*[»\"'„“”]?"
    rf"(?:\s+[«\"'„“”]?[\w][\w.\-]*[»\"'„“”]?){{0,3}})\s*$",
)
_INLINE_IP_RE = re.compile(
    r"(?<![А-ЯЁA-Z])(?P<form>ИП)\s+(?P<name>[А-ЯЁ][а-яё\-]+(?:\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.|\s+[А-ЯЁ]\.){0,2})",
)
# Маркер подписи только в начале строки — «отнестись с уважением»
# в середине фразы не открывает зону подписи.
_SIGNOFF_RE = re.compile(
    r"^\s*(?:с\s+уважением|с\s+наилучшим|с\s+почтением|"
    r"best\s+regards|kind\s+regards|warm\s+regards|sincerely|yours\s+truly|--\s*$)",
    re.IGNORECASE,
)
_QUOTED_PART_RE = re.compile(
    r"^\s*>|писал\(а\)\s*:?\s*$|\bwrote\s*:?\s*$|"
    r"^-{2,}.*(?:forwarded|переслан|original)|"
    r"<[^>\s]+@[^>\s]+>\s*:?\s*$",
    re.IGNORECASE,
)
# Шапка пересланного письма — граница только блоком (>=2 подряд) или
# уже после «С уважением»: одиночная «Тема: …» в тексте отправителя —
# его же строка, а не цитата (среднее ревью-2).
_QUOTE_HEADER_RE = re.compile(
    r"^\s*(?:от|from|кому|to|отправлено|sent|дата|date|тема|subject)\s*:",
    re.IGNORECASE,
)
# Дисклеймер после подписи («Данное письмо является собственностью ООО …»)
# — чужая организация, зону обрываем.
_DISCLAIMER_RE = re.compile(
    r"^\s*(?:данное\s+письмо|настоящее\s+письмо|сообщение\s+является|"
    r"this\s+(?:e-?mail|message)\s+is|внимание[!:]|confidential)",
    re.IGNORECASE,
)


def ensure_company_ref(client: Client) -> Company | None:
    """Attach a Company row for a client with a company label.

    Текстовое ``company`` / ``company_key`` остаётся ключом маршрутизации;
    ``company_ref`` — карточка юрлица (коллеги, ИНН, объединение).

    Args:
        client: saved Client (needs pk).

    Returns:
        Linked Company, or None when the label is empty.
    """
    if not client.pk:
        return None
    key = (client.company_key or "").strip()
    if not key:
        return cast("Company | None", client.company_ref)
    org = cast("Company | None", Company.objects.filter(company_key=key).first())
    if org is None:
        try:
            # Savepoint: without it a lost create-race aborts the whole
            # caller transaction on Postgres — the fallback read would
            # raise InternalError and the inbound letter is skipped.
            with transaction.atomic():
                org = Company.objects.create(name=(client.company or "").strip() or key)
        except IntegrityError:
            org = cast("Company | None", Company.objects.filter(company_key=key).first())
    if org is None:
        return cast("Company | None", client.company_ref)
    if client.company_ref_id != org.pk:
        Client.objects.filter(pk=client.pk).update(company_ref=org)
        client.company_ref_id = org.pk
        client.company_ref = org
    _ensure_member(org, client)
    return org


def _ensure_member(org: Company, client: Client) -> None:
    """Create a CompanyMember row if this contact is not listed yet."""
    exists = CompanyMember.objects.filter(company=org, client=client).exists()
    if exists:
        return
    CompanyMember.objects.create(
        company=org,
        client=client,
        account=client.account,
    )


def append_client_note(client: Client, line: str) -> None:
    """Append one line to ``client.notes``; idempotent by exact substring.

    Notes are the manager-visible place for non-authoritative hints —
    canonical fields stay human-written.
    """
    line = line.strip()
    if not line or line in (client.notes or ""):
        return
    client.notes = f"{client.notes}\n{line}" if client.notes else line
    client.save(update_fields=["notes", "updated_at"])


def enrich_client_company(client: Client, *, subject: str = "", body: str = "") -> bool:
    """Fill an empty ``company`` label: verified lead, else the signature.

    ``_resolve_client`` returns existing cards early, so a contact created
    without a label stayed unlabeled forever — letters piled up while no
    Company card existed (переписка есть, карточки нет). A verified lead is
    trusted (audit M1); the letter itself yields only a signature-zone
    guess. A filled label is never overwritten — human input beats a guess.

    Args:
        client: saved Client.
        subject: letter subject — scanned for quoted org forms.
        body: letter body — only the signature zone is scanned.

    Returns:
        True when the label was written (Company card linked by ``save()``).
    """
    if not client.pk or (client.company or "").strip():
        return False
    candidate = _verified_lead_company(client)
    source = "lead"
    if not candidate:
        candidate = company_guess_from_letter(subject=subject, body=body)
        source = "letter"
    if not candidate:
        return False
    client.company = candidate
    # Точечная запись: полный save() мог бы затирать параллельные правки
    # менеджера в других полях между чтением и обработкой письма.
    client.save(update_fields=["company", "company_key", "updated_at"])
    logger.info("crm_client_company_enriched client=%s source=%s", client.pk, source)
    return True


def _verified_lead_company(client: Client) -> str:
    """Latest verified lead's company label for this card's email."""
    from leads.models import Lead

    label = (
        Lead.objects.filter(contact_verified=True)
        .filter(Q(email__iexact=client.email) | Q(client=client))
        .exclude(company="")
        .order_by("-created_at")
        .values_list("company", flat=True)
        .first()
    )
    return " ".join((label or "").split())[:200]


def company_guess_from_letter(*, subject: str = "", body: str) -> str:
    """Org-label guess from the sender's signature zone, then the subject.

    Inside a real sign-off block («С уважением, …») quoted forms win first
    — the usual signature spelling; a line that is nothing but the org
    name («ООО СпецКомлект-С») and inline «ИП Фамилия И.О.» follow.
    Without a sign-off marker only standalone/ИП qualify: a quoted org
    mid-sentence («просим счёт от ООО "Рога"») names a third party too
    often. The subject yields only quoted forms. Our own «ООО "Хогон"»
    is skipped — it leaks from forwarded manager letters.
    """
    zone, from_marker = _signature_zone(body)
    for line in zone:
        if _DISCLAIMER_RE.search(line):
            break
        if from_marker:
            for quoted in _QUOTED_ORG_RE.finditer(line):
                label = _format_org_label(quoted["form"], quoted["name"])
                if label and not _is_own_company(label):
                    return label
        for regex in (_STANDALONE_ORG_RE, _INLINE_IP_RE):
            found = regex.search(line)
            if found is not None:
                label = _format_org_label(found["form"], found["name"])
                if label and not _is_own_company(label):
                    return label
    for quoted in _QUOTED_ORG_RE.finditer(subject or ""):
        label = _format_org_label(quoted["form"], quoted["name"])
        if label and not _is_own_company(label):
            return label
    return ""


def _signature_zone(body: str) -> tuple[list[str], bool]:
    """Sender's sign-off lines, and whether a marker opened them.

    Quoted history («… писал(а):», «> …», forwarded headers) is cut
    first — a manager's signature inside it must not become the
    customer's company. A forwarded-header line («От:», «Тема:») cuts
    only after the sender's sign-off or as a run of two — a lone
    «Тема: …» in the sender's own text is not a quote. With a sign-off
    marker the zone runs from it to the cut (up to 10 non-empty lines).
    Without one the zone is the last two non-empty lines — the caller
    then accepts only standalone org lines, not mid-sentence mentions.
    """
    lines: list[str] = []
    seen_signoff = False
    header_run = 0
    for raw in (body or "").splitlines():
        if _QUOTE_HEADER_RE.search(raw):
            if seen_signoff:
                break
            header_run += 1
            if header_run >= 2:
                del lines[-(header_run - 1) :]
                break
            lines.append(raw)
            continue
        header_run = 0
        if _QUOTED_PART_RE.search(raw):
            break
        if _SIGNOFF_RE.search(raw):
            seen_signoff = True
        lines.append(raw)
    marker = next(
        (index for index, line in enumerate(lines) if _SIGNOFF_RE.search(line)),
        None,
    )
    if marker is not None:
        return [line for line in lines[marker:] if line.strip()][:10], True
    return [line for line in lines if line.strip()][-2:], False


def _format_org_label(form: str, name: str) -> str:
    """Canonical label «Форма «Имя»» (ИП without quotes)."""
    name = " ".join(name.split()).strip(".,;:–—-«»\"'„“”")
    if not name:
        return ""
    if form == "ИП":
        return f"ИП {name}"[:200]
    return f"{form} «{name}»"[:200]


def _is_own_company(label: str) -> bool:
    """True for our own org name — must not become a customer card."""
    from leads.services import normalize_company_label

    return normalize_company_label(label) in _OWN_COMPANY_KEYS


def colleague_clients(client: Client) -> QuerySet[Client]:
    """Other active cards of the same company (FK or normalized key)."""
    qs = Client.objects.filter(is_active=True).exclude(pk=client.pk)
    if client.company_ref_id:
        return qs.filter(company_ref_id=client.company_ref_id)
    key = (client.company_key or "").strip()
    if not key:
        return qs.none()
    return qs.filter(company_key=key)


def similar_clients(client: Client) -> QuerySet[Client]:
    """Likely duplicates: same company or same phone, different email."""
    qs = Client.objects.filter(is_active=True).exclude(pk=client.pk)
    clauses = Q()
    key = (client.company_key or "").strip()
    if key:
        clauses |= Q(company_key=key)
    if client.company_ref_id:
        clauses |= Q(company_ref_id=client.company_ref_id)
    digits = (client.phone_digits or "").strip()
    if len(digits) >= 10:
        clauses |= Q(phone_digits=digits)
    if not clauses:
        return qs.none()
    return qs.filter(clauses).distinct()


def merge_companies(
    target: Company,
    sources: list[Company],
    *,
    actor: Any = None,
) -> dict[str, int]:
    """Move clients/members from ``sources`` onto ``target``, then delete sources.

    Args:
        target: surviving company card.
        sources: duplicates to absorb.
        actor: unused (reserved for timeline); merge is structural.

    Returns:
        Counts of moved clients and members.
    """
    del actor
    moved = {"clients": 0, "members": 0}
    with transaction.atomic():
        for source in sources:
            if source.pk == target.pk:
                continue
            moved["clients"] += Client.objects.filter(company_ref=source).update(
                company_ref=target,
            )
            moved["members"] += CompanyMember.objects.filter(company=source).update(
                company=target,
            )
            _absorb_outreach(target, source)
            source.delete()
        seen: set[tuple[int | None, int | None]] = set()
        for member in CompanyMember.objects.filter(company=target).order_by("pk"):
            key = (member.client_id, member.account_id)
            if key in seen:
                member.delete()
                continue
            seen.add(key)
    return moved


def _absorb_outreach(target: Company, source: Company) -> None:
    """Keep marks, the comment, and planned calls when two companies collapse."""
    from django.utils import timezone

    from crm.models import PlannedTouch
    from crm.outreach import touch_dedupe_key

    if source.phone:
        from crm.phones import join_phone_numbers

        target.phone = join_phone_numbers(target.phone, source.phone)
    for field_name in ("contact_name", "email", "website", "city", "region", "niche", "relevance"):
        if not getattr(target, field_name) and getattr(source, field_name):
            setattr(target, field_name, getattr(source, field_name))
    if source.comment and source.comment not in (target.comment or ""):
        target.comment = f"{target.comment}\n\n{source.comment}".strip()
    if target.assignee_id is None and source.assignee_id:
        target.assignee = source.assignee
    if target.next_contact_at is None:
        target.next_contact_at = source.next_contact_at
    target.work_labels.add(*source.work_labels.all())
    target.save()
    for touch in PlannedTouch.objects.filter(company=source):
        day = timezone.localtime(touch.starts_at).date()
        new_key = touch_dedupe_key(target.pk, touch.kind, day)
        if PlannedTouch.objects.filter(dedupe_key=new_key).exclude(pk=touch.pk).exists():
            touch.delete()
            continue
        touch.company = target
        touch.dedupe_key = new_key
        touch.save(update_fields=["company", "dedupe_key"])
