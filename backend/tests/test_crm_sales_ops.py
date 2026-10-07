"""CRM ops: company auto-link, quote copy/order, РОП report, sibling warning."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import Client as DjClient
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from accounts.models import ClientAccount
from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from cabinet.models import Order, SpecList, SpecListItem
from crm.company import colleague_clients, merge_companies
from crm.models import Client, Company, Quote, QuoteItem, QuoteStatus
from crm.quote_ops import (
    create_order_from_quote,
    create_quote_from_spec,
    duplicate_quote,
    sibling_open_quotes,
)
from crm.reports import build_sales_report
from crm.tasks import send_weekly_sales_report
from leads.models import Lead

User = get_user_model()


def _superuser() -> User:
    return User.objects.create_superuser(
        username="rop",
        email="rop@example.com",
        password="password12",
    )


@pytest.mark.django_db
def test_client_save_creates_company_ref_and_colleague() -> None:
    """Текстовая компания → карточка Company + коллеги по одному юрлицу."""
    a = Client.objects.create(
        name="Иван",
        email="ivan-co@example.com",
        company='ООО "Ромашка"',
    )
    b = Client.objects.create(
        name="Мария",
        email="maria-co@example.com",
        company='ООО "Ромашка"',
    )
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.company_ref_id is not None
    assert a.company_ref_id == b.company_ref_id
    assert Company.objects.filter(pk=a.company_ref_id).count() == 1
    assert colleague_clients(a).get().email == "maria-co@example.com"


@pytest.mark.django_db
def test_merge_companies_moves_clients() -> None:
    """Две карточки юрлица сливаются: клиенты остаются на целевой."""
    left = Company.objects.create(name="Альфа Плюс")
    right = Company.objects.create(name="Альфа Дубль")
    Client.objects.create(name="A", email="a-mrg@example.com", company_ref=left)
    Client.objects.create(name="B", email="b-mrg@example.com", company_ref=right)
    moved = merge_companies(left, [right])
    assert moved["clients"] == 1
    assert not Company.objects.filter(pk=right.pk).exists()
    assert Client.objects.filter(company_ref=left).count() == 2


@pytest.mark.django_db
def test_duplicate_quote_copies_lines_as_draft() -> None:
    """Копия КП — новый номер, черновик, позиции сохранены."""
    admin = _superuser()
    client = Client.objects.create(name="К", email="quote-dup@example.com")
    src = Quote.objects.create(client=client, created_by=admin, comment="срок 5 дней")
    QuoteItem.objects.create(quote=src, sku_code="DA24", quantity=2, unit_price=Decimal("10.00"))
    copy = duplicate_quote(src, author=admin)
    assert copy.pk != src.pk
    assert copy.status == QuoteStatus.DRAFT
    assert copy.number != src.number
    assert copy.comment == "срок 5 дней"
    assert list(copy.items.values_list("sku_code", "quantity")) == [("DA24", 2)]


@pytest.mark.django_db
def test_create_order_from_quote_reuses_open_order() -> None:
    """Повтор «создать заказ» не плодит второй незакрытый заказ."""
    admin = _superuser()
    client = Client.objects.create(name="К", email="quote-ord@example.com")
    quote = Quote.objects.create(client=client, created_by=admin, status=QuoteStatus.ACCEPTED)
    QuoteItem.objects.create(quote=quote, sku_code="SA10", quantity=1)
    first, created = create_order_from_quote(quote)
    assert created is True
    assert first.items.get().sku_code == "SA10"
    again, created = create_order_from_quote(quote)
    assert created is False
    assert again.pk == first.pk
    assert Order.objects.filter(quote=quote).count() == 1


@pytest.mark.django_db
def test_create_quote_from_spec_needs_crm_card() -> None:
    """Спецификация ЛК → черновик КП на карточке клиента."""
    admin = _superuser()
    account = ClientAccount.objects.create(email="spec-q@example.com", name="Spec Acc")
    client = Client.objects.create(
        name="Spec",
        email="spec-q@example.com",
        account=account,
    )
    spec = SpecList.objects.create(account=account, name="Объект X")
    SpecListItem.objects.create(spec=spec, sku_code="HVDF", quantity=4, position=0)
    quote = create_quote_from_spec(spec, author=admin)
    assert quote is not None
    assert quote.client_id == client.pk
    assert quote.items.get().sku_code == "HVDF"


@pytest.mark.django_db
def test_sibling_open_quotes_warns_about_colleague() -> None:
    """Открытое КП коллеги по компании видно как предупреждение."""
    admin = _superuser()
    a = Client.objects.create(name="A", email="sib-a@example.com", company="СибСтрой")
    b = Client.objects.create(name="B", email="sib-b@example.com", company="СибСтрой")
    Quote.objects.create(client=a, created_by=admin, status=QuoteStatus.SENT)
    found = sibling_open_quotes(b)
    assert len(found) == 1
    assert found[0].client_id == a.pk


@pytest.mark.django_db
def test_sales_report_counts_manager_funnel() -> None:
    """Отчёт РОП: заявка/КП менеджера попадают в его строку."""
    manager = User.objects.create_user(
        username="mgr-rep",
        email="mgr-rep@example.com",
        password="password12",
        is_staff=True,
        first_name="Пётр",
    )
    Group.objects.get_or_create(name=GROUP_MANAGER)
    manager.groups.add(Group.objects.get(name=GROUP_MANAGER))
    lead = Lead.objects.create(
        name="Клиент",
        email="funnel@example.com",
        message="x" * 20,
        assignee=manager,
        status=Lead.LeadStatus.DONE,
        processed_by=manager,
        processed_at=timezone.now(),
    )
    Quote.objects.create(client=lead.client, created_by=manager, status=QuoteStatus.DRAFT)
    report = build_sales_report(since=timezone.now() - timedelta(days=7), user=None)
    row = next(r for r in report["managers"] if r["user_id"] == manager.pk)
    assert row["leads_done"] == 1
    assert row["quotes_created"] == 1
    assert report["totals"]["quotes_created"] >= 1


@pytest.mark.django_db
def test_sales_report_admin_page_and_weekly_mail(settings) -> None:
    """Страница отчёта открывается; beat-задача шлёт письмо на LEAD_NOTIFY_EMAIL."""
    settings.LEAD_NOTIFY_EMAIL = "rop-inbox@example.com"
    admin = _superuser()
    Group.objects.get_or_create(name=GROUP_ADMIN)
    admin.groups.add(Group.objects.get(name=GROUP_ADMIN))
    page = DjClient()
    page.force_login(admin)
    response = page.get(reverse("admin:crm_client_sales_report"))
    assert response.status_code == 200
    assert "Отчёт по менеджерам" in response.content.decode()

    send_weekly_sales_report()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["rop-inbox@example.com"]
    assert "Отчёт по работе менеджеров" in mail.outbox[0].body


@pytest.mark.django_db
def test_quote_duplicate_and_order_views_are_post_only() -> None:
    """GET на копию КП / заказ из КП не пишет в БД."""
    admin = _superuser()
    client = Client.objects.create(name="К", email="post-only@example.com")
    quote = Quote.objects.create(client=client, created_by=admin)
    page = DjClient()
    page.force_login(admin)
    dup = reverse("admin:crm_quote_duplicate", args=[quote.pk])
    order_url = reverse("admin:crm_quote_create_order", args=[quote.pk])
    assert page.get(dup).status_code == 302
    assert Quote.objects.count() == 1
    assert page.get(order_url).status_code == 302
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_quote_kanban_set_status_json() -> None:
    """Kanban POST /set-status/ меняет статус КП."""
    admin = _superuser()
    client = Client.objects.create(name="К", email="kanban-q@example.com")
    quote = Quote.objects.create(client=client, created_by=admin)
    page = DjClient()
    page.force_login(admin)
    response = page.post(
        reverse("admin:crm_quote_set_status", args=[quote.pk]),
        data='{"status": "rejected"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.REJECTED


@pytest.mark.django_db
def test_quote_board_js_posts_to_quote_set_status() -> None:
    """JS канбана КП бьёт в /admin/crm/quote/<id>/set-status/, не в заявки."""
    from django.conf import settings as django_settings

    src = (django_settings.BASE_DIR / "static/admin/js/hoocon-admin-quotes-board.js").read_text(
        encoding="utf-8",
    )
    assert "/admin/crm/quote/" in src
    assert "application/x-hoocon-quote-pk" in src
    assert "accepted" in src


@pytest.mark.django_db
def test_weekly_sales_report_periodic_task_exists() -> None:
    """Миграция ставит понедельник 08:00 Europe/Moscow."""
    task = PeriodicTask.objects.get(name="crm.send_weekly_sales_report")
    assert task.task == "crm.send_weekly_sales_report"
    assert task.enabled is True


@pytest.mark.django_db
def test_manager_sales_report_is_scoped() -> None:
    """Менеджер на странице отчёта видит только свою строку."""
    mgr = User.objects.create_user(
        username="scoped-mgr",
        email="scoped-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    mgr.user_permissions.add(Permission.objects.get(codename="view_client"))
    other = User.objects.create_user(
        username="other-mgr",
        email="other-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    c1 = Client.objects.create(name="1", email="sc1@example.com")
    c2 = Client.objects.create(name="2", email="sc2@example.com")
    Quote.objects.create(client=c1, created_by=mgr)
    Quote.objects.create(client=c2, created_by=other)
    report = build_sales_report(since=None, user=mgr)
    assert report["scoped"] is True
    assert [row["user_id"] for row in report["managers"]] == [mgr.pk]
    assert report["managers"][0]["quotes_created"] == 1
    assert report["totals"]["quotes_created"] == 1
