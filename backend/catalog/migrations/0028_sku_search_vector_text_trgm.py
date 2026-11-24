"""Smart search groundwork: pg_trgm + SKU vector gains description/analog.

1. ``pg_trgm`` extension — trigram similarity for typo tolerance
   («превод» → «привод», «hva5m» → «HVA-5NM») in catalog ``?q=`` and site
   ``/api/search/``. GIN trigram index on ``sku_code`` backs the ``%``
   operator lookup; name/title similarity is scored over seq scan (tables
   are small) so no extra indexes are created for them.
2. ``search_vector`` trigger now also indexes ``description`` (weight B —
   the application text users search by, e.g. «для регулирования
   заслонок») and ``analog_belimo_code`` (weight C — the verified analog
   code only). HTML markup is stripped from description before
   vectorising. Raw ``analogs_text`` must NOT be indexed: card policy
   (``_drop_unverified_analog_lines``, see 95f9d311) hides unverified
   analog lines, and indexing them would publish hidden codes via search.
3. Backfill recomputes every existing SKU vector.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

# Trigger function: weighted FTS vector
# (name A, sku_code A, slug B, description B, analog_belimo_code C).
TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION catalog_sku_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.sku_code, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.slug, '')), 'B') ||
        setweight(
            to_tsvector(
                'russian',
                coalesce(regexp_replace(NEW.description, '<[^>]+>', ' ', 'g'), '')
            ),
            'B'
        ) ||
        setweight(to_tsvector('russian', coalesce(NEW.analog_belimo_code, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

PREVIOUS_TRIGGER_FUNCTION_SQL = """
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

# Rebind trigger to the extended column list (UPDATE OF cannot be altered
# in place — drop and recreate under the same name).
DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS sku_search_vector_update_trigger ON catalog_sku;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER sku_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF name, sku_code, slug, description, analog_belimo_code
    ON catalog_sku
    FOR EACH ROW EXECUTE FUNCTION catalog_sku_search_vector_update();
"""

PREVIOUS_CREATE_TRIGGER_SQL = """
CREATE TRIGGER sku_search_vector_update_trigger
    BEFORE INSERT OR UPDATE OF name, sku_code, slug ON catalog_sku
    FOR EACH ROW EXECUTE FUNCTION catalog_sku_search_vector_update();
"""

# Backfill search_vector for existing rows (trigger only fires on writes).
BACKFILL_SQL = """
UPDATE catalog_sku SET search_vector =
    setweight(to_tsvector('russian', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(sku_code, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(slug, '')), 'B') ||
    setweight(
        to_tsvector(
            'russian',
            coalesce(regexp_replace(description, '<[^>]+>', ' ', 'g'), '')
        ),
        'B'
    ) ||
    setweight(to_tsvector('russian', coalesce(analog_belimo_code, '')), 'C');
"""


class Migration(migrations.Migration):
    """pg_trgm + extended SKU FTS vector (description + analog_belimo_code)."""

    dependencies = [
        ("catalog", "0027_alter_sku_analog_belimo_code_help"),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            sql=TRIGGER_FUNCTION_SQL,
            reverse_sql=PREVIOUS_TRIGGER_FUNCTION_SQL,
        ),
        migrations.RunSQL(
            sql=DROP_TRIGGER_SQL,
            reverse_sql=PREVIOUS_CREATE_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=CREATE_TRIGGER_SQL,
            reverse_sql=DROP_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddIndex(
            model_name="sku",
            index=GinIndex(
                fields=["sku_code"],
                name="catalog_sku_code_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
