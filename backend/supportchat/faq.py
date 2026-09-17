"""FAQ queries — single source of truth (Admin ``FaqItem``)."""

from __future__ import annotations

from typing import Any

from supportchat.models import FaqItem

CHAT_FAQ_LIMIT = 10
HOME_FAQ_LIMIT = 12
SEO_FAQ_LIMIT = 40


def _display_question(item: FaqItem, *, short: bool) -> str:
    if short:
        return (item.question_short or item.question).strip()
    return item.question.strip()


def _serialize_item(item: FaqItem, *, short_question: bool) -> dict[str, Any]:
    return {
        "id": int(item.pk),
        "question": _display_question(item, short=short_question),
        "answer": str(item.answer).strip(),
    }


def chat_faq_items(*, limit: int = CHAT_FAQ_LIMIT) -> list[dict[str, Any]]:
    """Active FAQ chips for the support widget (``show_in_chat``)."""
    qs = FaqItem.objects.filter(is_active=True, show_in_chat=True).order_by("order", "id")[: max(1, limit)]
    return [_serialize_item(row, short_question=True) for row in qs]


def home_faq_items(*, limit: int = HOME_FAQ_LIMIT) -> list[dict[str, Any]]:
    """FAQ block on the home page (``show_on_home``)."""
    qs = FaqItem.objects.filter(is_active=True, show_on_home=True).order_by("order", "id")[: max(1, limit)]
    return [_serialize_item(row, short_question=False) for row in qs]


def seo_faq_tuples(
    canonical_path: str,
    *,
    limit: int = SEO_FAQ_LIMIT,
) -> tuple[tuple[str, str], ...]:
    """Question/answer pairs for FAQPage JSON-LD."""
    if canonical_path == "/":
        qs = FaqItem.objects.filter(is_active=True, show_on_home=True)
    else:
        qs = FaqItem.objects.filter(is_active=True)
    rows = qs.order_by("order", "id").values("question", "answer")[: max(1, limit)]
    pairs: list[tuple[str, str]] = []
    for row in rows:
        question = str(row["question"]).strip()
        answer = str(row["answer"]).strip()
        if question and answer:
            pairs.append((question, answer))
    return tuple(pairs)
