"""ETL package for catalog import (Tilda JSON → Django ORM).

Pipeline: extract → normalize/validate → load. Bad rows → quarantine CSV.
Spec: docs/data-quality-etl.md §4.
"""

from __future__ import annotations
