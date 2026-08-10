"""Add search_vector + trigger for Page FTS (site-wide search).

Spec: ПЛАН §6 — глобальный поиск по сайту; Page участвует наряду с
SKU / Article / News.
"""

from __future__ import annotations

import django.contrib.postgres.search
from django.db import migrations

PAGE_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION content_page_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.body, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_PAGE_TRIGGER_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS content_page_search_vector_update();
"""

CREATE_PAGE_TRIGGER_SQL = """
CREATE TRIGGER content_page_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF title, body ON content_page
    FOR EACH ROW EXECUTE FUNCTION content_page_search_vector_update();
"""

DROP_PAGE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS content_page_search_vector_update_trigger ON content_page;
"""

BACKFILL_PAGE_SQL = """
UPDATE content_page SET search_vector =
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(body, '')), 'B');
"""

CREATE_PAGE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS content_page_search_vector_idx
    ON content_page USING GIN (search_vector);
"""

DROP_PAGE_INDEX_SQL = """
DROP INDEX IF EXISTS content_page_search_vector_idx;
"""


class Migration(migrations.Migration):
    """Add search_vector + trigger + GIN index for Page FTS."""

    dependencies = [
        ("content", "0003_article_cover_excerpt"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunSQL(
            sql=PAGE_TRIGGER_FUNCTION_SQL,
            reverse_sql=DROP_PAGE_TRIGGER_FUNCTION_SQL,
        ),
        migrations.RunSQL(
            sql=CREATE_PAGE_TRIGGER_SQL,
            reverse_sql=DROP_PAGE_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=BACKFILL_PAGE_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CREATE_PAGE_INDEX_SQL,
            reverse_sql=DROP_PAGE_INDEX_SQL,
        ),
    ]
