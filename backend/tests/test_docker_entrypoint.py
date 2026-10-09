"""Container bootstrap and prod compose invariants."""

from __future__ import annotations

from pathlib import Path

import yaml

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent


def test_docker_entrypoint_seeds_wiki_after_migrate() -> None:
    """Deploy runs seed_wiki so bundled HTML dashboards refresh on prod."""
    text = (_BACKEND / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    migrate_idx = text.index("migrate --noinput")
    seed_idx = text.index("seed_wiki")
    collect_idx = text.index("collectstatic --noinput")
    assert migrate_idx < seed_idx < collect_idx


def _prod_services() -> dict[str, dict]:
    compose = yaml.safe_load((_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    return compose["services"]


def test_prod_compose_persists_private_media_in_every_app_service() -> None:
    """private_media жил внутри контейнера: записи звонков и документы терялись при деплое.

    web, worker and beat must share one host directory so files written by
    Celery (IMAP attachments, Mango recordings) are served by web.
    """
    services = _prod_services()
    for name in ("web", "celery_worker", "celery_beat"):
        mounts = services[name]["volumes"]
        assert "/var/www/hoocon/private_media:/app/private_media" in mounts, name


def test_private_media_never_baked_into_image_and_is_backed_up() -> None:
    """Локальные приватные файлы попадали в Docker-образ; в бэкапе их не было."""
    ignore = (_BACKEND / ".dockerignore").read_text(encoding="utf-8").split()
    assert "private_media/" in ignore
    assert ".env" in ignore
    backup = (_ROOT / "scripts" / "backup-vps.sh").read_text(encoding="utf-8")
    assert "/var/www/hoocon/private_media" in backup
    assert "private_media.tar.gz" in backup
    deploy = (_ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "WWW_PRIVATE_MEDIA:-/var/www/hoocon/private_media" in deploy
    assert "chown 1000:1000 '${WWW_PRIVATE_MEDIA}'" in deploy


def test_only_web_bootstraps_database() -> None:
    """migrate/seed/collectstatic гонялись в worker и beat параллельно с web."""
    entrypoint = (_BACKEND / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    gate = entrypoint.index('if [ "${RUN_BOOTSTRAP:-1}" = "1" ]')
    assert gate < entrypoint.index("migrate --noinput")
    services = _prod_services()
    assert "RUN_BOOTSTRAP" not in services["web"]["environment"]
    for name in ("celery_worker", "celery_beat"):
        assert services[name]["environment"]["RUN_BOOTSTRAP"] == "0", name
