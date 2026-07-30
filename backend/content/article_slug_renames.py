"""Canonical article slug renames (Tilda ID prefixes → readable ЧПУ).

Spec: docs/seo-url-migration.md — keep old path as 301, new slug as canonical.
Also relocates ``article_covers/<old-slug>/…`` files to ``article_covers/<new>/…``
so media folder names match the public URL.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from content.models import Article
from redirects.models import Redirect
from redirects.pathutils import normalize_path

logger = logging.getLogger(__name__)

# old slug (Tilda / scrape) → canonical public slug
ARTICLE_SLUG_RENAMES: dict[str, str] = {
    "4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov": ("spetsifikatsiya-modelnogo-ryada-privodov"),
    "2zbgj89cp1-primenenie-privodov-v-sistemah-ventilyat": ("primenenie-privodov-v-sistemah-ventilyatsii"),
    "85zdfbzso1-protivopozharnie-vs-vzrivozaschischennie": ("protivopozharnye-vs-vzryvozashchishchennye-privody"),
    "gu8x3sz4e1-osobennosti-elektroprivodov-ventilyatsii": ("protivopozharnye-vs-dymoudaleniya-privody"),
    "vvme9fxcy1-ognezaderzhivayuschii-klapan-printsip-ra": ("ognezaderzhivayushchii-klapan"),
    "j1en0umao1-sharovie-krani-vidi-konstruktsiya-primen": ("sharovye-krany-vidy-konstruktsiya"),
    "62uel9kue1-ventilyatsiya-v-metro": ("ventilyatsiya-v-metro"),
}


def relocate_article_cover_to_slug(article: Article) -> str | None:
    """Move cover file into ``article_covers/<article.slug>/`` when folder drifts.

    Args:
        article: Article with optional ``cover`` FileField.

    Returns:
        New relative media path, or ``None`` when no move was needed / possible.
    """
    if not article.cover or not article.slug:
        return None
    old_name = (article.cover.name or "").replace("\\", "/")
    parts = PurePosixPath(old_name).parts
    if len(parts) < 3 or parts[0] != "article_covers":
        return None
    folder = parts[1]
    if folder == article.slug:
        return None
    basename = parts[-1]
    new_name = f"article_covers/{article.slug}/{basename}"
    if not default_storage.exists(old_name):
        logger.warning(
            "article_cover_missing slug=%s path=%s",
            article.slug,
            old_name,
        )
        return None
    if default_storage.exists(new_name):
        # Destination already has the file — just repoint the field.
        article.cover.name = new_name
        article.save(update_fields=["cover", "updated_at"])
        try:
            default_storage.delete(old_name)
        except OSError:
            logger.warning("article_cover_old_delete_failed path=%s", old_name)
        return new_name

    with default_storage.open(old_name, "rb") as src:
        default_storage.save(new_name, ContentFile(src.read()))
    article.cover.name = new_name
    article.save(update_fields=["cover", "updated_at"])
    try:
        default_storage.delete(old_name)
    except OSError:
        logger.warning("article_cover_old_delete_failed path=%s", old_name)
    logger.info(
        "article_cover_relocated slug=%s from=%s to=%s",
        article.slug,
        old_name,
        new_name,
    )
    return new_name


def relocate_all_article_covers() -> list[tuple[str, str]]:
    """Relocate every article cover whose folder ≠ current slug.

    Returns:
        List of ``(old_path, new_path)`` moves.
    """
    moved: list[tuple[str, str]] = []
    for article in Article.objects.exclude(cover="").iterator():
        old = article.cover.name
        new = relocate_article_cover_to_slug(article)
        if new:
            moved.append((old, new))
    return moved


def apply_article_slug_renames() -> list[tuple[str, str]]:
    """Rename articles and upsert 301 ``/statyi/{old}`` → ``/statyi/{new}``.

    If both old and new Article rows exist, keep the new row and delete the old
    one (body/cover already on the survivor). If only old exists, rename in place.
    After slug fixes, relocate cover files into ``article_covers/<slug>/``.

    Returns:
        List of ``(old_slug, new_slug)`` pairs that were ensured (rename and/or
        redirect).
    """
    applied: list[tuple[str, str]] = []
    for old_slug, new_slug in ARTICLE_SLUG_RENAMES.items():
        old_article = Article.objects.filter(slug=old_slug).first()
        new_article = Article.objects.filter(slug=new_slug).first()
        if old_article is not None and new_article is not None:
            if old_article.pk != new_article.pk:
                old_article.delete()
        elif old_article is not None:
            old_article.slug = new_slug
            old_article.save(update_fields=["slug", "updated_at"])

        Redirect.objects.update_or_create(
            from_path=normalize_path(f"/statyi/{old_slug}"),
            defaults={
                "to_path": normalize_path(f"/statyi/{new_slug}"),
                "status_code": Redirect.HTTP_MOVED_PERMANENTLY,
                "is_active": True,
            },
        )
        applied.append((old_slug, new_slug))

    relocate_all_article_covers()
    return applied
