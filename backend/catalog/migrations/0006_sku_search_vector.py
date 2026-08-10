"""Add search_vector SearchVectorField + trigger for auto-FTS on SKU.

Spec: ПЛАН §6 Iter 2 — Postgres FTS по SKU (SearchVector name+sku_code+slug).
Trigger maintains search_vector on INSERT/UPDATE so the Python layer never
needs to compute it. Russian config for Cyrillic stemming.
"""

from __future__ import annotations

from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models


# Trigger function: weighted FTS vector (name A, sku_code A, slug B).
TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION catalog_sku_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.sku_code, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.slug, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_TRIGGER_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS catalog_sku_search_vector_update();
"""

# Trigger: call the function BEFORE INSERT or UPDATE on catalog_sku.
CREATE_TRIGGER_SQL = """
CREATE TRIGGER sku_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF name, sku_code, slug ON catalog_sku
    FOR EACH ROW EXECUTE FUNCTION catalog_sku_search_vector_update();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS sku_search_vector_update_trigger ON catalog_sku;
"""

# Backfill search_vector for existing rows (trigger only fires on new writes).
BACKFILL_SQL = """
UPDATE catalog_sku SET search_vector =
    setweight(to_tsvector('russian', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(sku_code, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(slug, '')), 'B');
"""

# GIN index for fast FTS queries.
CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS catalog_sku_search_vector_idx
    ON catalog_sku USING GIN (search_vector);
"""

DROP_INDEX_SQL = """
DROP INDEX IF EXISTS catalog_sku_search_vector_idx;
"""


class Migration(migrations.Migration):
    """Add search_vector column + trigger + GIN index for SKU FTS."""

    dependencies = [
        ("catalog", "0005_productfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="sku",
            name="search_vector",
            field=SearchVectorField(blank=True, editable=False, null=True),
        ),
        migrations.RunSQL(
            sql=TRIGGER_FUNCTION_SQL,
            reverse_sql=DROP_TRIGGER_FUNCTION_SQL,
        ),
        migrations.RunSQL(
            sql=CREATE_TRIGGER_SQL,
            reverse_sql=DROP_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CREATE_INDEX_SQL,
            reverse_sql=DROP_INDEX_SQL,
        ),
    ]
