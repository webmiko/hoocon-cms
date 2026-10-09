"""Tests for the remaining ЛК roadmap slices.

Covers: quote PDF → ClientDocument on SENT (+ notification email), public
analog lookup (ЛК-10), .xlsx spec import (ЛК-9), client-card merge action.
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.base import ContentFile
from django.test import Client as DjangoClient
from django.test import RequestFactory
from django.urls import reverse

from cabinet.spec_import import SpecParseError, parse_spec_xlsx
from catalog.models import SKU, AnalogMap, Category, Product
from crm.models import (
    Client,
    ClientDocument,
    DocumentKind,
    EmailMessage,
    Quote,
    QuoteStatus,
)
from crm.services import merge_clients
from leads.models import Lead


def _sku(code: str = "HVA-TEST-5") -> SKU:
    """Create a minimal catalog SKU for analog/spec tests."""
    cat, _ = Category.objects.get_or_create(name="Приводы", slug="lk-drives")
    product, _ = Product.objects.get_or_create(name="HVA серия", slug="lk-hva", category=cat)
    sku, _ = SKU.objects.get_or_create(
        sku_code=code,
        defaults={
            "product": product,
            "name": f"Привод {code}",
            "slug": f"lk-{code.lower()}",
        },
    )
    return sku


def _client(email: str, company: str = "Акме") -> Client:
    return Client.objects.create(name="Покупатель", email=email, company=company)


def _quote(client: Client) -> Quote:
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Покупатель",
        email=client.email,
        client=client,
    )
    lead.items.create(sku_code="HVA-5NM", quantity=2)
    from crm.services import create_quote_from_lead

    quote, _ = create_quote_from_lead(lead, author=None)
    return quote


@pytest.mark.django_db
def test_quote_sent_creates_pdf_document_and_notifies(settings) -> None:
    """SENT → PDF lands as ClientDocument(quote_pdf) + outbound email queued."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client = _client("quote-pdf@acme.test")
    quote = _quote(client)

    from crm.quote_docs import ensure_quote_pdf_document, notify_quote_issued

    doc = ensure_quote_pdf_document(quote)
    assert doc.kind == DocumentKind.QUOTE_PDF
    assert doc.client_id == client.pk
    assert doc.file.name.endswith(".pdf")
    assert "client_docs/" in doc.file.name

    # Idempotent: second call refreshes the same document.
    again = ensure_quote_pdf_document(quote)
    assert again.pk == doc.pk
    assert ClientDocument.objects.filter(quote=quote).count() == 1

    msg = notify_quote_issued(quote, send_now=False, document=doc)
    assert msg.to_email == client.email
    assert quote.number in msg.subject
    assert EmailMessage.objects.filter(client=client, subject__contains=quote.number).exists()
    att = msg.attachments.get()
    assert att.filename.endswith(".pdf")
    assert att.content_type == "application/pdf"
    assert att.size > 0


@pytest.mark.django_db
def test_quote_admin_sent_transition_issues_document() -> None:
    """Admin status → SENT runs the document/notification pipeline once."""
    client = _client("quote-admin@acme.test")
    quote = _quote(client)
    admin = User.objects.create_superuser("root@x.test", "root@x.test", "pw")

    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = admin
    request.session = SessionStore()  # type: ignore[assignment]
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]

    from types import SimpleNamespace

    from django.contrib.admin.sites import site

    model_admin = site._registry[Quote]
    form = SimpleNamespace(instance=quote, save_m2m=lambda: None)

    def admin_save() -> None:
        model_admin.save_model(request, quote, form=form, change=True)
        model_admin.save_related(request, form, formsets=[], change=True)

    quote.status = QuoteStatus.SENT
    admin_save()

    quote.refresh_from_db()
    assert quote.sent_at is not None
    doc = ClientDocument.objects.get(quote=quote, kind=DocumentKind.QUOTE_PDF)
    assert doc.file
    assert EmailMessage.objects.filter(client=client).exists()

    # Re-save in SENT does not queue a second notification.
    EmailMessage.objects.filter(client=client).delete()
    admin_save()
    assert not EmailMessage.objects.filter(client=client).exists()


@pytest.mark.django_db
def test_analog_lookup_endpoint() -> None:
    """GET /api/catalog/analogs/ matches foreign code → Hoocon SKU."""
    sku = _sku()
    AnalogMap.objects.create(
        brand="Belimo",
        foreign_code="NM24A-SR",
        sku=sku,
        torque_nm=10,
        voltage="AC/DC 24V",
    )
    api = DjangoClient()
    found = api.get("/api/catalog/analogs/", {"brand": "belimo", "code": "nm24a sr"})
    assert found.status_code == 200
    body = found.json()
    assert body["count"] == 1
    assert body["matches"][0]["sku_code"] == sku.sku_code
    # Brand filter narrows; unknown code → empty.
    miss = api.get("/api/catalog/analogs/", {"brand": "siemens", "code": "NM24ASR"})
    assert miss.json()["count"] == 0
    assert api.get("/api/catalog/analogs/").status_code == 400


def _xlsx(rows: list[tuple[str, object]], headers: tuple[str, ...]) -> io.BytesIO:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.mark.django_db
def test_spec_xlsx_parser_resolves_sku_and_analog() -> None:
    """Parser finds the code/qty columns; foreign codes hit AnalogMap."""
    sku = _sku()
    AnalogMap.objects.create(brand="Belimo", foreign_code="NM24A", sku=sku)

    buf = _xlsx(
        [
            (sku.sku_code, 2),
            ("NM24A", 5),
            ("UNKNOWN-XYZ", 1),
        ],
        headers=("Артикул", "Количество"),
    )
    rows = parse_spec_xlsx(buf)
    assert len(rows) == 3
    assert rows[0].sku is not None and not rows[0].via_analog
    assert rows[1].sku is not None and rows[1].via_analog
    assert rows[2].sku is None


@pytest.mark.django_db
def test_spec_xlsx_parser_rejects_garbage() -> None:
    """A sheet without an article column raises a user-facing error."""
    buf = _xlsx([("a", 1)], headers=("foo", "bar"))
    with pytest.raises(SpecParseError):
        parse_spec_xlsx(buf)


@pytest.mark.django_db
def test_merge_clients_moves_relations() -> None:
    """Merge moves leads/quotes/docs/orders to target; source deactivated."""
    from cabinet.models import Order

    target = _client("main@acme.test")
    dup = _client("alias@acme.test", company="Акме")
    Lead.objects.create(lead_type=Lead.LeadType.RFQ, name="П", email=dup.email, client=dup)
    Quote.objects.create(client=dup, status=QuoteStatus.DRAFT)
    Order.objects.create(client=dup, number="З-дубль")
    ClientDocument.objects.create(
        client=dup,
        kind=DocumentKind.OTHER,
        title="doc.pdf",
        file=ContentFile(b"x", name="doc.pdf"),
    )

    moved = merge_clients(target, [dup])
    dup.refresh_from_db()
    assert not dup.is_active
    assert moved["leads"] == 1
    assert moved["quotes"] == 1
    assert moved["orders"] == 1
    assert moved["documents"] == 1
    assert target.leads.count() == 1
    assert target.quotes.count() == 1
    # Timeline gets a merge note.
    assert target.activities.filter(subject__contains="Объединение").exists()


@pytest.mark.django_db
def test_merge_clients_action_requires_two() -> None:
    """Admin action warns when fewer than two cards are selected."""
    admin = User.objects.create_superuser("merge@x.test", "merge@x.test", "pw")
    page = DjangoClient()
    page.force_login(admin)
    client = _client("solo@acme.test")
    response = page.post(
        reverse("admin:crm_client_changelist"),
        {"action": "merge_clients_action", "_selected_action": [client.pk]},
    )
    assert response.status_code in (200, 302)
    assert Client.objects.filter(email="solo@acme.test").exists()


@pytest.mark.django_db
def test_merge_clients_moves_all_relations() -> None:
    """Merge reassigns leads/quotes/orders/RMA/memberships and deactivates source."""
    from cabinet.models import Order, RmaCase
    from crm.models import Activity, Company, CompanyMember

    target = _client("merge-main@acme.test", company="")
    source = _client("merge-dup@acme.test", company="Акме Дубль")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Д",
        email=source.email,
        client=source,
    )
    Activity.objects.create(client=source, activity_type="other", subject="звонок")
    EmailMessage.objects.create(
        client=source, direction="outbound", status="sent", to_email=source.email, subject="s", body="b"
    )
    Quote.objects.create(client=source, lead=lead, status=QuoteStatus.SENT)
    Order.objects.create(client=source, number="З-merge-1")
    RmaCase.objects.create(client=source, subject="Скрип")
    company = Company.objects.create(name="Акме Мерж")
    CompanyMember.objects.create(company=company, client=source, role="buyer")

    moved = merge_clients(target, [source])

    assert moved["leads"] == 1 and moved["quotes"] == 1
    assert moved["orders"] == 1 and moved["rma_cases"] == 1
    assert moved["emails"] == 1 and moved["activities"] >= 1
    source.refresh_from_db()
    target.refresh_from_db()
    assert source.is_active is False
    assert target.company == "Акме Дубль"  # пустое поле цели дополнено
    assert target.leads.count() == 1 and target.orders.count() == 1
    assert company.members.get().client_id == target.pk


@pytest.mark.django_db
def test_merge_clients_keeps_target_account() -> None:
    """Привязка ЛК остаётся у цели; у источника забирается только если у цели нет."""
    from accounts.models import ClientAccount

    target = _client("merge-a@acme.test")
    source = _client("merge-b@acme.test")
    acc_target = ClientAccount.objects.create(email=target.email, auth_mode="password")
    acc_source = ClientAccount.objects.create(email=source.email, auth_mode="password")
    target.account = acc_target
    target.save(update_fields=["account"])
    source.account = acc_source
    source.save(update_fields=["account"])

    merge_clients(target, [source])
    target.refresh_from_db()
    source.refresh_from_db()
    assert target.account_id == acc_target.pk
    assert source.account_id == acc_source.pk  # чужой аккаунт не отбираем

    # У цели нет аккаунта → переезжает с источника.
    target2 = _client("merge-c@acme.test")
    merge_clients(target2, [source])
    target2.refresh_from_db()
    assert target2.account_id == acc_source.pk


@pytest.mark.django_db
def test_contact_match_and_lookup_helpers() -> None:
    """contact_matches_client / find_client_for_lead / by_email backfill."""
    from crm.services import (
        contact_matches_client,
        find_client_for_lead,
        get_or_create_client_by_email,
    )

    client = _client("match@acme.test", company="Акме")
    assert contact_matches_client(client, email="match@acme.test", name="Покупатель", company="акме")
    assert not contact_matches_client(client, email="other@acme.test", name="", company="")
    assert not contact_matches_client(client, email="match@acme.test", name="Другой", company="")

    lead = Lead.objects.create(lead_type=Lead.LeadType.RFQ, name="П", email="match@acme.test")
    assert find_client_for_lead(lead).pk == client.pk
    # Без карточки с таким email → None (сигнал лидов создаёт карточку
    # при сохранении, поэтому проверяем на непривязанном объекте).
    orphan = Lead(lead_type=Lead.LeadType.RFQ, name="П", email="none@acme.test")
    assert find_client_for_lead(orphan) is None

    made = get_or_create_client_by_email(email="new@acme.test", name="Новый", phone="+7")
    assert made.name == "Новый" and made.phone == "+7"
    again = get_or_create_client_by_email(email="new@acme.test", company="Акме")
    assert again.pk == made.pk and again.company == "Акме"  # дополнение пустых полей


@pytest.mark.django_db
def test_email_template_render_and_pick() -> None:
    """Шаблон подставляет {имя}/{компания}; неактивный шаблон не берётся."""
    from crm.models import EmailTemplate
    from crm.services import (
        email_template_context_for_client,
        get_active_email_template,
        render_email_template,
    )

    tpl = EmailTemplate.objects.create(
        name="Приветствие",
        subject="Здравствуйте, {имя}",
        body="Ваша компания: {компания}.",
        is_active=True,
    )
    client = _client("tpl@acme.test")
    subject, body = render_email_template(
        tpl,
        context=email_template_context_for_client(client),
    )
    assert "Покупатель" in subject and "Акме" in body
    assert get_active_email_template(tpl.pk).pk == tpl.pk
    tpl.is_active = False
    tpl.save()
    assert get_active_email_template(tpl.pk) is None
    assert get_active_email_template("abc") is None


@pytest.mark.django_db
def test_outbound_email_sends_attachment(settings) -> None:
    """send_crm_email прикрепляет EmailAttachment к исходящему письму."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from django.core import mail

    from crm.services import create_outbound_email
    from crm.tasks import send_crm_email

    client = _client("attach@acme.test")
    msg = create_outbound_email(
        client=client,
        subject="КП",
        body="см. вложение",
        send_now=False,
        attachments=[("kp.pdf", "application/pdf", b"%PDF-1.4 fake")],
    )
    send_crm_email(msg.pk)
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.attachments and sent.attachments[0][0] == "kp.pdf"


@pytest.mark.django_db
def test_analog_lookup_rejects_symbol_only_code_and_hides_unpublished() -> None:
    """M31: код «---» не отдаёт первые 10 строк карты; скрытый SKU не виден в подборе."""
    published = _sku("HVA-PUB-5")
    hidden = _sku("HVA-HIDDEN-5")
    hidden.is_published = False
    hidden.save(update_fields=["is_published"])
    AnalogMap.objects.create(brand="Belimo", foreign_code="LM24A", sku=published)
    AnalogMap.objects.create(brand="Belimo", foreign_code="SM24A", sku=hidden)
    api = DjangoClient()

    assert api.get("/api/catalog/analogs/", {"code": "---"}).status_code == 400
    assert api.get("/api/catalog/analogs/", {"code": "SM24A"}).json()["count"] == 0
    assert api.get("/api/catalog/analogs/", {"code": "LM24A"}).json()["count"] == 1


def test_quote_vat_rounds_half_up_and_label_drops_zeros() -> None:
    """НДС округлялся банковским HALF_EVEN, ставка печаталась как «22.00%»."""
    from decimal import Decimal

    from crm.quote_pdf import vat_amount_rub, vat_rate_label

    # 0.125 ₽ → 0.13 (HALF_EVEN gave 0.12).
    assert vat_amount_rub(Decimal("0.625"), Decimal("20")) == Decimal("0.13")
    assert vat_rate_label(Decimal("22.00")) == "22"
    assert vat_rate_label(Decimal("12.50")) == "12.5"
    assert vat_rate_label(Decimal("20")) == "20"


@pytest.mark.django_db
def test_quote_pdf_prints_local_dates_and_clean_vat(monkeypatch: pytest.MonkeyPatch, settings) -> None:
    """Дата КП в PDF была по UTC: КП от 00:30 МСК печаталось вчерашним числом."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from reportlab.pdfgen.canvas import Canvas

    from crm.quote_pdf import render_quote_pdf

    settings.TIME_ZONE = "Europe/Moscow"
    quote = _quote(_client("quote-tz@acme.test"))
    item = quote.items.first()
    item.unit_price = Decimal("0.625")
    item.quantity = 1
    item.save()
    Quote.objects.filter(pk=quote.pk).update(
        created_at=datetime(2026, 10, 8, 21, 30, tzinfo=UTC), vat_rate=Decimal("20.00")
    )
    quote.refresh_from_db()

    drawn: list[str] = []
    for method in ("drawString", "drawRightString"):
        original = getattr(Canvas, method)

        def _capture(self, x, y, text, *a, _orig=original, **kw):  # noqa: ANN001, ANN202
            drawn.append(str(text))
            return _orig(self, x, y, text, *a, **kw)

        monkeypatch.setattr(Canvas, method, _capture)

    render_quote_pdf(quote)
    assert "Дата: 09.10.2026" in drawn
    assert "НДС 20%: 0.13 ₽" in drawn


@pytest.mark.django_db
def test_call_str_uses_local_time(settings) -> None:
    """Call.__str__ показывал время звонка по UTC."""
    from datetime import UTC, datetime

    from crm.models import Call

    settings.TIME_ZONE = "Europe/Moscow"
    call = Call(
        entry_id="tz-1", from_number="7915", to_number="101", started_at=datetime(2026, 10, 8, 21, 5, tzinfo=UTC)
    )
    assert str(call).endswith("09.10 00:05")
