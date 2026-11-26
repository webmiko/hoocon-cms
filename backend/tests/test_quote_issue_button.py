"""КП: кнопка «Выдать клиенту» и подсказка, как отправить КП."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as HttpClient
from django.urls import reverse

from crm.models import Client, Quote, QuoteItem, QuoteStatus
from crm.quote_ops import build_issue_panel, issued_message

User = get_user_model()


def _admin() -> Any:
    return User.objects.create_superuser(username="qi-root", email="qi-root@example.com", password="password12")


def _quote(email: str = "buyer@klimat.ru", **fields: Any) -> Quote:
    client = Client.objects.create(name="Иван", email=email)
    return Quote.objects.create(client=client, **fields)


def _form(quote: Quote, **extra: str) -> dict[str, str]:
    data = {
        "status": QuoteStatus.DRAFT,
        "client": str(quote.client_id),
        "lead": "",
        "created_by": "",
        "comment": "",
        "vat_rate": "22.00",
        "valid_until": "",
        "items-TOTAL_FORMS": "0",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
    }
    data.update(extra)
    return data


def _login() -> HttpClient:
    http = HttpClient()
    http.force_login(_admin())
    return http


@pytest.mark.django_db
def test_draft_page_explains_how_to_send_the_quote() -> None:
    quote = _quote()
    QuoteItem.objects.create(quote=quote, sku_code="A-1", quantity=1, sort_order=0)

    html = _login().get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    assert "Как отправить КП клиенту" in html
    assert "Выдать клиенту" in html
    assert "buyer@klimat.ru" in html
    assert 'name="_issue_quote"' in html
    # The button must sit inside the offer form so it saves the edits too.
    assert html.index('id="quote_form"') < html.index('name="_issue_quote"')


@pytest.mark.django_db
def test_issue_button_turns_draft_into_sent() -> None:
    quote = _quote()
    item = QuoteItem.objects.create(quote=quote, sku_code="A-1", quantity=2, sort_order=0)
    data = _form(
        quote,
        _issue_quote="1",
        **{
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-0-id": str(item.pk),
            "items-0-quote": str(quote.pk),
            "items-0-sku": "",
            "items-0-sku_code": "A-1",
            "items-0-quantity": "2",
            "items-0-unit_price": "",
            "items-0-sort_order": "0",
        },
    )

    with patch("crm.quote_docs.ensure_quote_pdf_document", side_effect=RuntimeError("no pdf in test")):
        response = _login().post(reverse("admin:crm_quote_change", args=[quote.pk]), data)

    quote.refresh_from_db()
    assert response.status_code == 302
    assert quote.status == QuoteStatus.SENT
    assert quote.sent_at is not None


@pytest.mark.django_db
def test_issue_button_refuses_an_empty_quote() -> None:
    quote = _quote()

    response = _login().post(
        reverse("admin:crm_quote_change", args=[quote.pk]),
        _form(quote, _issue_quote="1"),
        follow=True,
    )

    quote.refresh_from_db()
    assert quote.status == QuoteStatus.DRAFT
    assert quote.sent_at is None
    assert "добавьте хотя бы одну позицию" in response.content.decode()


@pytest.mark.django_db
def test_plain_save_keeps_the_draft() -> None:
    quote = _quote()

    _login().post(reverse("admin:crm_quote_change", args=[quote.pk]), _form(quote))

    quote.refresh_from_db()
    assert quote.status == QuoteStatus.DRAFT


@pytest.mark.django_db
def test_sent_page_has_no_issue_button() -> None:
    quote = _quote(status=QuoteStatus.SENT)

    html = _login().get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    assert "КП выдано" in html
    assert 'name="_issue_quote"' not in html


@pytest.mark.django_db
def test_stub_mailbox_is_called_out_before_issuing() -> None:
    quote = _quote(email="79001112233@call.invalid")

    panel = build_issue_panel(quote, can_change=True)
    html = _login().get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    assert panel["email_ok"] is False
    assert "нет рабочей почты" in html
    assert "письмо не отправлено" in issued_message(quote)


@pytest.mark.django_db
def test_issued_message_names_the_mailbox() -> None:
    quote = _quote()
    quote.refresh_from_db()

    assert "buyer@klimat.ru" in issued_message(quote)


@pytest.mark.django_db
def test_panel_shows_total_and_warns_about_missing_prices() -> None:
    quote = _quote()
    QuoteItem.objects.create(quote=quote, sku_code="A-1", quantity=2, unit_price="1500.00", sort_order=0)
    QuoteItem.objects.create(quote=quote, sku_code="B-2", quantity=1, sort_order=1)

    panel = build_issue_panel(quote, can_change=True)
    html = _login().get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    assert panel["items"] == 2
    assert panel["missing_price"] == 1
    assert str(panel["total"]) == "3000.00"
    assert "3000,00" in html or "3000.00" in html
    assert "не указана цена" in html


@pytest.mark.django_db
def test_sent_quote_has_answer_buttons_that_move_the_status() -> None:
    quote = _quote(status=QuoteStatus.SENT)
    http = _login()

    page = http.get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()
    response = http.post(reverse("crm-workspace-quote-answer", args=[quote.pk]), {"answer": "accepted"})

    quote.refresh_from_db()
    assert "Клиент согласился" in page
    assert "Клиент отказался" in page
    assert response.status_code == 302
    assert quote.status == QuoteStatus.ACCEPTED


@pytest.mark.django_db
def test_answer_rejects_unknown_status_and_draft_quotes() -> None:
    draft = _quote(email="draft-answer@klimat.ru")
    http = _login()

    http.post(reverse("crm-workspace-quote-answer", args=[draft.pk]), {"answer": "accepted"})
    http.post(reverse("crm-workspace-quote-answer", args=[draft.pk]), {"answer": "draft"})

    draft.refresh_from_db()
    assert draft.status == QuoteStatus.DRAFT
    assert http.get(reverse("crm-workspace-quote-answer", args=[draft.pk])).status_code == 405


@pytest.mark.django_db
def test_add_page_explains_the_steps_and_defaults_the_author() -> None:
    admin = _admin_user_for_add()
    http = HttpClient()
    http.force_login(admin)

    response = http.get(reverse("admin:crm_quote_add"))
    html = response.content.decode()

    assert "Как создать КП" in html
    assert "Кому и по какой заявке" in html
    assert response.context["adminform"].form.initial["created_by"] == admin.pk


def _admin_user_for_add() -> Any:
    return User.objects.create_superuser(username="qi-add", email="qi-add@example.com", password="password12")


@pytest.mark.django_db
def test_accepted_quote_shows_a_create_order_button_in_the_panel() -> None:
    quote = _quote(status=QuoteStatus.ACCEPTED)
    QuoteItem.objects.create(quote=quote, sku_code="A-1", quantity=2, unit_price="1000.00", sort_order=0)

    html = _login().get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    assert "Клиент согласился" in html
    assert f'formaction="{reverse("admin:crm_quote_create_order", args=[quote.pk])}"' in html
    # The button is in the panel inside the quote form, not only in the toolbar.
    assert html.index('id="quote_form"') < html.index(
        f'formaction="{reverse("admin:crm_quote_create_order", args=[quote.pk])}"'
    )


@pytest.mark.django_db
def test_create_order_button_posts_and_the_panel_then_opens_the_order() -> None:
    quote = _quote(status=QuoteStatus.ACCEPTED)
    QuoteItem.objects.create(quote=quote, sku_code="A-1", quantity=2, unit_price="1000.00", sort_order=0)
    http = _login()

    response = http.post(reverse("admin:crm_quote_create_order", args=[quote.pk]))
    html = http.get(reverse("admin:crm_quote_change", args=[quote.pk])).content.decode()

    order = quote.orders.get()
    assert response.status_code == 302
    assert "Открыть заказ" in html
    assert order.number in html
    assert (
        'formaction="' + reverse("admin:crm_quote_create_order", args=[quote.pk]) + '"'
        not in html.split("Открыть заказ")[0].split('id="quote_form"')[1]
    )


@pytest.mark.django_db
def test_user_without_order_permission_is_told_who_creates_the_order() -> None:
    quote = _quote(status=QuoteStatus.ACCEPTED)

    panel = build_issue_panel(quote, can_change=True, can_order=False)

    assert panel["can_order"] is False
    assert panel["order_forbidden"] is True
