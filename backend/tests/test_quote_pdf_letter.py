"""Каркас PDF КП: письмо, цена уже с НДС, общие ТТХ только если они совпали."""

from __future__ import annotations

from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from catalog.models import SKU, Attribute, AttributeValue, Category, Product
from crm.models import Client, Quote, QuoteItem, QuoteStatus
from crm.quote_pdf import quote_table_widths, render_quote_pdf, vat_included_rub
from tests.quote_pdf_text import pdf_text


def test_vat_included_is_taken_out_of_the_gross_price() -> None:
    """НДС в КП сидит внутри цены: 1000 × 22 / 122 = 180,33, а не 220 сверху."""
    assert vat_included_rub(Decimal("1000.00"), Decimal("22")) == Decimal("180.33")
    assert vat_included_rub(Decimal("122.00"), Decimal("22")) == Decimal("22.00")
    # 0,03 × 22 / 122 = 0,005409 → 0,01. HALF_EVEN оставил бы 0,00? нет, 0,005 → банк 0,00
    # на копейках следующая цифра 5, half-up даёт 0,01.
    assert vat_included_rub(Decimal("0.03"), Decimal("22")) == Decimal("0.01")
    assert vat_included_rub(Decimal("100.00"), Decimal("0")) == Decimal("0.00")


def test_quote_table_columns_fill_the_page_and_do_not_spill() -> None:
    """Сумма ширин равна полосе текста: лишняя колонка не вылезает на поле."""
    usable = A4[0] - 28 * mm
    for show_prices in (True, False):
        widths = quote_table_widths(usable, show_prices=show_prices)
        assert sum(widths) == pytest.approx(usable)
        assert min(widths) > 0


def _sku(code: str, name: str) -> SKU:
    category, _ = Category.objects.get_or_create(name="Приводы КП", slug="qp-drives")
    product, _ = Product.objects.get_or_create(name="SA серия", slug="qp-sa", category=category)
    sku, _ = SKU.objects.get_or_create(
        sku_code=code,
        defaults={"product": product, "name": name, "slug": f"qp-{code.lower()}"},
    )
    return sku


def _attr(sku: SKU, slug: str, title: str, value: str) -> None:
    attribute, _ = Attribute.objects.get_or_create(slug=slug, defaults={"name": title})
    AttributeValue.objects.create(sku=sku, attribute=attribute, value=value)


@pytest.mark.django_db
def test_quote_letter_shows_gross_price_and_shared_specs_only() -> None:
    """Письмо: цена 1000 ₽ уже с НДС 22%, чужой IP в общие характеристики не попадает."""
    person = Client.objects.create(
        name="Марина",
        email="letter@acme.test",
        company="Акме Тест",
        phone="+7 900 000-00-00",
    )
    quote = Quote.objects.create(
        client=person,
        status=QuoteStatus.DRAFT,
        number="КП-100",
        comment="Поставка на объект в Пушкино.",
        vat_rate=Decimal("22.00"),
    )
    first = _sku("SA10FU24-DS", "SA10FU | Электропривод с пружинным возвратом, 10 Нм КРОМКА999")
    second = _sku("SA5FU24-DS", "SA5FU | Электропривод с пружинным возвратом, 5 Нм")
    _attr(first, "moment", "Момент", "10 Нм")
    _attr(second, "moment", "Момент", "5 Нм")
    _attr(first, "ip-rating", "Степень защиты", "IP54")
    _attr(second, "ip-rating", "Степень защиты", "IP20")
    _attr(first, "control", "Управление", "2-позиционное")
    _attr(second, "control", "Управление", "2-позиционное")
    QuoteItem.objects.create(
        quote=quote,
        sku=first,
        sku_code=first.sku_code,
        quantity=2,
        unit_price=Decimal("1000.00"),
    )
    QuoteItem.objects.create(
        quote=quote,
        sku=second,
        sku_code=second.sku_code,
        quantity=1,
        unit_price=Decimal("500.00"),
        sort_order=1,
    )

    text = " ".join(pdf_text(render_quote_pdf(quote)).split())
    assert "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ" in text
    assert "Для Акме Тест" in text
    assert "Получатель" in text
    assert "Здравствуйте, Марина!" in text
    assert "Цены указаны с НДС 22%" in text
    assert "СПЕЦИФИКАЦИЯ И ЦЕНЫ" in text
    assert "SA10FU24-DS" in text
    assert "10 Нм" in text
    assert "С пружинным возвратом" in text
    assert "КРОМКА999" in text
    assert "1000.00" in text
    assert "2000.00" in text
    # 1000×2 + 500 = 2500 уже с НДС. 2500 × 22 / 122 = 450,8196… → 450,82.
    # 2500 × 1,22 = 3050 было бы, если налог начислить сверху.
    assert "Итого: 2500.00" in text
    assert "В том числе НДС 22%: 450.82" in text
    assert "3050.00" not in text
    assert "Управление: 2-позиционное" in text
    assert "Степень защиты" not in text
    assert "УСЛОВИЯ" in text
    assert "не является офертой" in text
    assert "50% предоплата" in text
    assert "ст. 437" in text
    assert "5024199634" in text
    assert "24 месяца" in text
    assert "Поставка на объект в Пушкино." in text
