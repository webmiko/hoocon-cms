"""FAQ single source: Admin FaqItem drives API, JSON-LD and home scope."""

from __future__ import annotations

import pytest
from django.test import Client

from config.seo.json_ld import build_json_ld
from config.seo.head import SeoHeadContext
from supportchat.faq import chat_faq_items, home_faq_items, seo_faq_tuples
from supportchat.models import FaqItem


@pytest.mark.django_db
def test_chat_faq_uses_question_short() -> None:
    FaqItem.objects.all().delete()
    FaqItem.objects.create(
        question="Можно ли заменить SA10FU230-DS на DA10FU230-DS?",
        question_short="SA вместо DA?",
        answer="Нет.",
        order=1,
        is_active=True,
        show_in_chat=True,
    )
    items = chat_faq_items()
    assert items[0]["question"] == "SA вместо DA?"


@pytest.mark.django_db
def test_home_faq_uses_full_question() -> None:
    FaqItem.objects.all().delete()
    FaqItem.objects.create(
        question="Можно ли заменить SA10FU230-DS на DA10FU230-DS?",
        question_short="SA вместо DA?",
        answer="Нет.",
        order=1,
        is_active=True,
        show_on_home=True,
    )
    items = home_faq_items()
    assert items[0]["question"].startswith("Можно ли заменить")


@pytest.mark.django_db
def test_support_faq_api_scopes() -> None:
    FaqItem.objects.all().delete()
    FaqItem.objects.create(
        question="Home only",
        answer="a",
        order=1,
        is_active=True,
        show_on_home=True,
        show_in_chat=False,
    )
    FaqItem.objects.create(
        question="Chat chip",
        question_short="Chip",
        answer="b",
        order=2,
        is_active=True,
        show_in_chat=True,
    )
    client = Client()

    chat = client.get("/api/support/faq/?scope=chat").json()
    assert chat["scope"] == "chat"
    assert [i["question"] for i in chat["items"]] == ["Chip"]

    home = client.get("/api/support/faq/?scope=home").json()
    assert home["scope"] == "home"
    assert [i["question"] for i in home["items"]] == ["Home only"]

    seo = client.get("/api/support/faq/?scope=seo&path=/faq").json()
    assert seo["scope"] == "seo"
    assert len(seo["items"]) == 2


@pytest.mark.django_db
def test_json_ld_home_uses_show_on_home_items() -> None:
    FaqItem.objects.all().delete()
    FaqItem.objects.create(
        question="SEO home Q",
        answer="SEO home A",
        order=1,
        is_active=True,
        show_on_home=True,
    )
    FaqItem.objects.create(
        question="Other Q",
        answer="Other A",
        order=2,
        is_active=True,
    )
    context = SeoHeadContext(
        canonical_path="/",
        page_title="Home",
        description="desc",
        noindex=False,
        og_type="website",
    )
    blocks = build_json_ld(context)
    faq_blocks = [b for b in blocks if b.get("@type") == "FAQPage"]
    assert len(faq_blocks) == 1
    names = [q["name"] for q in faq_blocks[0]["mainEntity"]]
    assert names == ["SEO home Q"]


@pytest.mark.django_db
def test_migration_seeds_home_faq_items() -> None:
    """After migrations, four home FAQ entries exist from former HOME_FAQ_ITEMS."""
    home = home_faq_items()
    questions = {item["question"] for item in home}
    assert "Как заказать и получить КП?" in questions
    assert "Как подобрать модель на сайте?" in questions
    assert any("SA10FU230" in q for q in questions)
