"""Smoke tests for container entrypoint bootstrap commands."""

from __future__ import annotations

from pathlib import Path


def test_docker_entrypoint_seeds_wiki_after_migrate() -> None:
    """Deploy runs seed_wiki so bundled HTML dashboards refresh on prod."""
    entrypoint = Path(__file__).resolve().parents[1] / "scripts" / "docker-entrypoint.sh"
    text = entrypoint.read_text(encoding="utf-8")
    migrate_idx = text.index("migrate --noinput")
    seed_idx = text.index("seed_wiki")
    collect_idx = text.index("collectstatic --noinput")
    assert migrate_idx < seed_idx < collect_idx
