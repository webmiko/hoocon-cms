"""Публичная оферта: цена с НДС 22% и предоплата только если её назвал счёт."""

from __future__ import annotations


def test_public_offer_includes_vat_and_invoice_prepayment() -> None:
    """Редакция 26.10.2026: цена уже с НДС, 7 дней только для склада, КП договор не заключает."""
    from content.management.commands.seed_site_content import PAGES

    body = PAGES["oferta"][1]
    assert "26.10.2026" in body
    assert "с НДС 22%" in body
    assert "не начисляется сверху" in body
    assert "50% предоплата" in body
    assert "Коммерческое предложение договор не заключает" in body
    assert "заменяет редакцию от 01.06.2025" in body
    assert "в течение 7 рабочих дней" in body
    assert "Позиции под заказ" in body
