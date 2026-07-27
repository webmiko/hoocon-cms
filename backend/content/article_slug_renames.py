"""Canonical article slug renames (Tilda ID prefixes → readable ЧПУ).

Spec: docs/seo-url-migration.md — keep old path as 301, new slug as canonical.
"""

from __future__ import annotations

from content.models import Article
from redirects.models import Redirect
from redirects.pathutils import normalize_path

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


def apply_article_slug_renames() -> list[tuple[str, str]]:
    """Rename articles and upsert 301 ``/statyi/{old}`` → ``/statyi/{new}``.

    If both old and new Article rows exist, keep the new row and delete the old
    one (body/cover already on the survivor). If only old exists, rename in place.

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
    return applied
