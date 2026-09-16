"""GigaChat knowledge base and system prompt (gigachat_kb.txt only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.seo.routes import PUBLIC_STATIC_ROUTES
from supportchat.gigachat.kb_branches import load_kb_branches
from supportchat.gigachat.knowledge import (
    build_faq_items_block,
    build_knowledge_context,
    build_site_routes_block,
)
from supportchat.gigachat.prompts import build_system_prompt
from supportchat.models import FaqItem


@pytest.mark.django_db
def test_faq_block_includes_all_active_not_only_chat_chips() -> None:
    """Блок FAQ для сборки KB берёт все активные FAQ."""
    FaqItem.objects.all().delete()
    FaqItem.objects.create(
        question="Только чат",
        answer="чип",
        order=1,
        is_active=True,
        show_in_chat=True,
    )
    FaqItem.objects.create(
        question="Только AI",
        answer="полный ответ",
        order=2,
        is_active=True,
        show_in_chat=False,
    )
    block = build_faq_items_block()
    assert "Только чат" in block
    assert "Только AI" in block


def test_site_routes_block_from_public_seo() -> None:
    """Разделы сайта — из PUBLIC_STATIC_ROUTES (для сборки файла)."""
    block = build_site_routes_block()
    assert "/catalog" in block
    assert PUBLIC_STATIC_ROUTES["/catalog"]["title"][:20] in block


@pytest.mark.django_db
def test_system_prompt_file_only_and_hvac_scope(settings) -> None:
    """Промпт full: только gigachat_kb.txt, без самодеятельности."""
    settings.GIGACHAT_MODE = "full"
    prompt = build_system_prompt()
    lowered = prompt.lower()
    assert "gigachat_kb.txt" in lowered
    assert "исключительно" in lowered or "только" in lowered
    assert "[ESCALATE]" in prompt
    assert "ворот" in lowered
    assert "додумывай" in lowered or "запрещено" in lowered


@pytest.mark.django_db
def test_knowledge_context_respects_size_limit() -> None:
    """Контекст не раздувается бесконечно."""
    ctx = build_knowledge_context(max_chars=500)
    assert len(ctx) <= 520


@pytest.mark.skipif(
    not Path(__file__)
    .resolve()
    .parents[1]
    .joinpath(
        "supportchat/data/gigachat_kb.txt",
    )
    .is_file(),
    reason="gigachat_kb.txt не собран",
)
@pytest.mark.django_db
def test_da2mu_query_includes_manual_torque_in_context(settings) -> None:
    settings.GIGACHAT_MODE = "full"
    """Вопрос по DA2MU: ветка мануала с 2 Н·м в контексте."""
    load_kb_branches.cache_clear()
    ctx = build_knowledge_context(user_query="Какой крутящий момент у DA2MU?")
    lowered = ctx.casefold()
    assert "da2mu" in lowered
    assert "2 нм" in lowered


@pytest.mark.skipif(
    not Path(__file__)
    .resolve()
    .parents[1]
    .joinpath(
        "supportchat/data/gigachat_kb.txt",
    )
    .is_file(),
    reason="gigachat_kb.txt не собран",
)
@pytest.mark.django_db
def test_mu_query_includes_policy_branch(settings) -> None:
    settings.GIGACHAT_MODE = "full"
    """По серии MU в контексте есть policy.bot и мануал."""
    load_kb_branches.cache_clear()
    ctx = build_knowledge_context(user_query="Расскажи про DA4MU")
    assert "policy.bot" in ctx
    assert "da4" in ctx.casefold() or "4 нм" in ctx.casefold()
