"""Add search_vector SearchVectorField + triggers for Article/News FTS.

Spec: ПЛАН §6 Iter 3 — FTS расширяем на Article/News (SearchVector на content).
Triggers maintain search_vector on INSERT/UPDATE so Python never computes it.
Weights: title = A (rank higher), body = B. Russian config for Cyrillic stemming.
"""

from __future__ import annotations

import django.contrib.postgres.search
from django.db import migrations


# ── Article trigger ───────────────────────────────────────────────────


ARTICLE_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION content_article_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.body, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_ARTICLE_TRIGGER_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS content_article_search_vector_update();
"""

CREATE_ARTICLE_TRIGGER_SQL = """
CREATE TRIGGER content_article_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF title, body ON content_article
    FOR EACH ROW EXECUTE FUNCTION content_article_search_vector_update();
"""

DROP_ARTICLE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS content_article_search_vector_update_trigger ON content_article;
"""

BACKFILL_ARTICLE_SQL = """
UPDATE content_article SET search_vector =
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(body, '')), 'B');
"""

CREATE_ARTICLE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS content_article_search_vector_idx
    ON content_article USING GIN (search_vector);
"""

DROP_ARTICLE_INDEX_SQL = """
DROP INDEX IF EXISTS content_article_search_vector_idx;
"""


# ── News trigger ──────────────────────────────────────────────────────


NEWS_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION content_news_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.body, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_NEWS_TRIGGER_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS content_news_search_vector_update();
"""

CREATE_NEWS_TRIGGER_SQL = """
CREATE TRIGGER content_news_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF title, body ON content_news
    FOR EACH ROW EXECUTE FUNCTION content_news_search_vector_update();
"""

DROP_NEWS_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS content_news_search_vector_update_trigger ON content_news;
"""

BACKFILL_NEWS_SQL = """
UPDATE content_news SET search_vector =
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(body, '')), 'B');
"""

CREATE_NEWS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS content_news_search_vector_idx
    ON content_news USING GIN (search_vector);
"""

DROP_NEWS_INDEX_SQL = """
DROP INDEX IF EXISTS content_news_search_vector_idx;
"""


class Migration(migrations.Migration):
    """Add search_vector + trigger + GIN index for Article and News FTS."""

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        # ── Article ───────────────────────────────────────────────────
        migrations.AddField(
            model_name="article",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunSQL(
            sql=ARTICLE_TRIGGER_FUNCTION_SQL,
            reverse_sql=DROP_ARTICLE_TRIGGER_FUNCTION_SQL,
        ),
        migrations.RunSQL(
            sql=CREATE_ARTICLE_TRIGGER_SQL,
            reverse_sql=DROP_ARTICLE_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=BACKFILL_ARTICLE_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CREATE_ARTICLE_INDEX_SQL,
            reverse_sql=DROP_ARTICLE_INDEX_SQL,
        ),
        # ── News ───────────────────────────────────────────────────────
        migrations.AddField(
            model_name="news",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunSQL(
            sql=NEWS_TRIGGER_FUNCTION_SQL,
            reverse_sql=DROP_NEWS_TRIGGER_FUNCTION_SQL,
        ),
        migrations.RunSQL(
            sql=CREATE_NEWS_TRIGGER_SQL,
            reverse_sql=DROP_NEWS_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=BACKFILL_NEWS_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CREATE_NEWS_INDEX_SQL,
            reverse_sql=DROP_NEWS_INDEX_SQL,
        ),
    ]
