"""Tests for FTS on Article/News (SearchVector on title + body) (TDD).

Spec: ПЛАН §6 Iter 3 — FTS расширяем на Article/News (поиск теперь и по контенту);
docs/readiness-backend-ux.md §2.2 — E-E-A-T content searchable.

Контракт:
- Article/News имеют `search_vector` (SearchVectorField), поддерживаемый
  Postgres-триггером (как у SKU в Iter 2).
- Веса: title = A, body = B (title-матч ранжирует выше body-матча).
- Russian config для кириллической стеммизации.
- GIN-индекс на search_vector для быстрых запросов.
"""

from __future__ import annotations

import pytest
from django.contrib.postgres.search import SearchQuery
from django.db import connection

# ── Schema / field presence ──────────────────────────────────────────


@pytest.mark.django_db
def test_article_has_search_vector_field() -> None:
    """Article model has a `search_vector` SearchVectorField."""
    from content.models import Article

    field = Article._meta.get_field("search_vector")
    assert field is not None
    assert field.__class__.__name__ == "SearchVectorField"
    # Not editable — maintained by DB trigger, not by Python code.
    assert field.editable is False


@pytest.mark.django_db
def test_news_has_search_vector_field() -> None:
    """News model has a `search_vector` SearchVectorField."""
    from content.models import News

    field = News._meta.get_field("search_vector")
    assert field is not None
    assert field.__class__.__name__ == "SearchVectorField"
    assert field.editable is False


# ── Trigger populates search_vector ───────────────────────────────────


@pytest.mark.django_db
def test_article_search_vector_populated_by_trigger() -> None:
    """Inserting an Article populates search_vector via DB trigger."""
    from content.models import Article

    art = Article.objects.create(
        title="Подбор электропривода для воздушных клапанов",
        slug="podbor-elektroprivoda",
        body="Электроприводы ОВК выбирают по моменту и напряжению.",
    )
    art.refresh_from_db()
    assert art.search_vector is not None
    # Russian stemming: 'подбор' → 'подб'
    assert "подб" in str(art.search_vector)


@pytest.mark.django_db
def test_news_search_vector_populated_by_trigger() -> None:
    """Inserting a News item populates search_vector via DB trigger."""
    from content.models import News

    n = News.objects.create(
        title="Анонс нового привода HVA-5NM",
        slug="anons-novogo-privoda",
        body="Компания Hoocon расширяет линейку приводов.",
    )
    n.refresh_from_db()
    assert n.search_vector is not None
    assert "анонс" in str(n.search_vector)


# ── FTS query matches ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_article_fts_matches_title() -> None:
    """FTS query on Article matches by title."""
    from content.models import Article

    # Unique stem — seed guides must not collide (подбор/привод appear there).
    Article.objects.create(
        title="Как подобрать ксилоквантный привод",
        slug="kak-podobrat-1",
        body="",
    )
    Article.objects.create(
        title="Не связанный контент",
        slug="drugoy-1",
        body="",
    )
    q = SearchQuery("ксилоквантный", config="russian")
    found = Article.objects.filter(search_vector=q)
    assert found.count() == 1
    assert found.first().title == "Как подобрать ксилоквантный привод"


@pytest.mark.django_db
def test_article_fts_matches_body() -> None:
    """FTS query on Article matches by body content."""
    from content.models import Article

    Article.objects.create(
        title="Гайд",
        slug="gayd-1",
        body="Подбор ксилоквантного привода по моменту и напряжению.",
    )
    Article.objects.create(
        title="Другой гайд",
        slug="gayd-2",
        body="Совершенно другая тема без нужных слов.",
    )
    q = SearchQuery("ксилоквантного", config="russian")
    found = Article.objects.filter(search_vector=q)
    assert found.count() == 1
    assert found.first().slug == "gayd-1"


@pytest.mark.django_db
def test_news_fts_matches_body() -> None:
    """FTS query on News matches by body content."""
    from content.models import News

    News.objects.create(
        title="Анонс",
        slug="anons-1",
        body="Запустили производство ксилоквантов в России.",
    )
    News.objects.create(
        title="Другая новость",
        slug="novost-2",
        body="Открыли новый склад.",
    )
    # Unique token — seed news (e.g. BR adapters) must not collide.
    q = SearchQuery("ксилоквант", config="russian")
    found = News.objects.filter(search_vector=q)
    assert found.count() == 1
    assert found.first().slug == "anons-1"


# ── Ranking: title (A) > body (B) ─────────────────────────────────────


@pytest.mark.django_db
def test_article_fts_title_ranks_higher_than_body() -> None:
    """Title match (weight A) ranks higher than body-only match (weight B).

    The trigger assigns weight A to title and B to body (verified by
    inspecting the search_vector text). Raw `ts_rank` (which preserves
    weights from the SearchVectorField) ranks title-match above body-match.

    Note: Django's ORM `SearchRank` casts SearchVectorField to text before
    passing to `ts_rank`, which strips weight markers — so we verify
    ranking via raw SQL that passes the field directly.
    """
    from content.models import Article

    # Body-only match (weight B).
    body_art = Article.objects.create(
        title="Краткий гайд",
        slug="body-match",
        body="Здесь упоминается ксилоквантный привод для ОВК.",
    )
    # Title match (weight A) — should rank higher.
    title_art = Article.objects.create(
        title="Ксилоквантный привод для ОВК",
        slug="title-match",
        body="Здесь нет нужных слов в теле.",
    )
    body_art.refresh_from_db()
    title_art.refresh_from_db()

    # Verify the trigger assigned correct weights in the vector.
    body_vec = str(body_art.search_vector)
    title_vec = str(title_art.search_vector)
    # Unique token — seed guides use «подбор» and would collide.
    assert "'ксилоквантн':" in body_vec and "B" in body_vec.split("'ксилоквантн':")[1][:2]
    assert "'ксилоквантн':" in title_vec and "A" in title_vec.split("'ксилоквантн':")[1][:2]

    # Raw ts_rank (passing SearchVectorField directly) ranks title above body.
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT slug
            FROM content_article
            WHERE search_vector @@ plainto_tsquery('russian', 'ксилоквантный')
            ORDER BY ts_rank(
              search_vector, plainto_tsquery('russian', 'ксилоквантный')
            ) DESC
            """,
        )
        slugs = [row[0] for row in cur.fetchall()]
    assert slugs[0] == "title-match"
    assert slugs[1] == "body-match"


# ── GIN index presence ──────────────────────────────────────────────


@pytest.mark.django_db
def test_article_search_vector_gin_index_exists() -> None:
    """GIN index on content_article.search_vector exists."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'content_article'
              AND indexname LIKE '%search_vector%'
            """,
        )
        names = [row[0] for row in cur.fetchall()]
    assert any("search_vector" in n for n in names), f"GIN index not found; got {names}"


@pytest.mark.django_db
def test_news_search_vector_gin_index_exists() -> None:
    """GIN index on content_news.search_vector exists."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'content_news'
              AND indexname LIKE '%search_vector%'
            """,
        )
        names = [row[0] for row in cur.fetchall()]
    assert any("search_vector" in n for n in names), f"GIN index not found; got {names}"


# ── Trigger updates on UPDATE ─────────────────────────────────────────


@pytest.mark.django_db
def test_article_search_vector_updates_on_title_change() -> None:
    """Trigger re-computes search_vector when title changes."""
    from content.models import Article

    art = Article.objects.create(
        title="Старый заголовок",
        slug="staraya-statya",
        body="",
    )
    art.refresh_from_db()
    old_vector = str(art.search_vector)
    art.title = "Новый заголовок про электроприводы"
    art.save()
    art.refresh_from_db()
    new_vector = str(art.search_vector)
    assert old_vector != new_vector
    assert "электропривод" in new_vector
