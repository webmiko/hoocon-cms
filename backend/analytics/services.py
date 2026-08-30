"""Record and aggregate first-party page hits."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import unquote, urlparse

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.http import HttpRequest
from django.utils import timezone

from analytics.models import ObjectType, PageDailyStat, SiteDailyStat

_MAX_PATH = 512
_MAX_TITLE = 255
_MAX_KEY = 255
_UV_TTL = 60 * 60 * 48  # 48h — covers timezone edge around midnight

_SKU_PATH = re.compile(r"^/catalog/([^/]+)/([^/]+)/?$")
_CATALOG_PATH = re.compile(r"^/catalog(?:/([^/]+))?/?$")
_ARTICLE_PATH = re.compile(r"^/statyi/([^/]+)/?$")
_NEWS_PATH = re.compile(r"^/novosti/([^/]+)/?$")
_PAGE_SLUGS = frozenset(
    {
        "company",
        "zavod",
        "faq",
        "kontakty",
        "oferta",
        "privacy-policy",
        "terms",
        "gde-kupit",
        "dokumentaciya",
    },
)
_LEAD_PATHS = frozenset({"/rfq", "/consultation", "/replacement"})


def normalize_path(raw: str) -> str:
    """Return a canonical SPA path (no query/hash; leading slash; no trailing slash).

    Args:
        raw: Client path or full URL fragment.

    Returns:
        Normalized path, or empty string if invalid.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" in text:
        text = urlparse(text).path or "/"
    text = text.split("?", 1)[0].split("#", 1)[0]
    text = unquote(text)
    if not text.startswith("/"):
        text = f"/{text}"
    # Collapse duplicate slashes; drop trailing slash except root.
    parts = [p for p in text.split("/") if p]
    text = "/" + "/".join(parts) if parts else "/"
    if len(text) > _MAX_PATH:
        return ""
    # Never track admin / API / static.
    lower = text.lower()
    if lower.startswith(("/admin", "/api/", "/static/", "/media/", "/__")):
        return ""
    return text


def classify_path(path: str) -> tuple[str, str]:
    """Infer object type and key from a normalized public path.

    Args:
        path: Output of :func:`normalize_path`.

    Returns:
        ``(object_type, object_key)``.
    """
    if path == "/":
        return ObjectType.HOME, ""
    if path == "/search" or path.startswith("/search/"):
        return ObjectType.SEARCH, ""
    if path in _LEAD_PATHS or path.rstrip("/") in _LEAD_PATHS:
        return ObjectType.LEAD, path.strip("/").split("/")[0]
    m = _SKU_PATH.match(path)
    if m:
        return ObjectType.SKU, m.group(2)[:_MAX_KEY]
    m = _CATALOG_PATH.match(path)
    if m:
        return ObjectType.CATALOG, (m.group(1) or "")[:_MAX_KEY]
    m = _ARTICLE_PATH.match(path)
    if m:
        return ObjectType.ARTICLE, m.group(1)[:_MAX_KEY]
    if path == "/statyi":
        return ObjectType.ARTICLE, ""
    m = _NEWS_PATH.match(path)
    if m:
        return ObjectType.NEWS, m.group(1)[:_MAX_KEY]
    if path == "/novosti":
        return ObjectType.NEWS, ""
    slug = path.strip("/")
    if slug in _PAGE_SLUGS and "/" not in slug:
        return ObjectType.PAGE, slug
    return ObjectType.OTHER, slug[:_MAX_KEY]


def ensure_visitor_id(request: HttpRequest) -> str:
    """Ensure a Django session exists and return its key (visitor id).

    Session cookie is an essential first-party cookie already used for CSRF/forms.

    Args:
        request: Django (or DRF ``._request``) request.

    Returns:
        Non-empty session key.
    """
    if not request.session.session_key:
        request.session.create()
    key = request.session.session_key or ""
    if not key:
        request.session.save()
        key = request.session.session_key or ""
    return key


def _uv_cache_key(kind: str, day: date, visitor_id: str, path: str = "") -> str:
    if kind == "site":
        return f"analytics:suv:{day.isoformat()}:{visitor_id}"
    return f"analytics:uv:{day.isoformat()}:{path}:{visitor_id}"


def _mark_unique(kind: str, day: date, visitor_id: str, path: str = "") -> bool:
    """Return True once per visitor/day(/path) using the shared cache."""
    key = _uv_cache_key(kind, day, visitor_id, path)
    # add() is atomic: True only on first set.
    return bool(cache.add(key, 1, timeout=_UV_TTL))


def record_page_hit(
    *,
    request: HttpRequest,
    path: str,
    title: str = "",
    object_type: str = "",
    object_key: str = "",
) -> bool:
    """Record one SPA pageview into daily aggregates.

    Args:
        request: Django request (session for unique visitors).
        path: Client path.
        title: Optional document title.
        object_type: Optional override (must be a valid ObjectType).
        object_key: Optional override key/slug.

    Returns:
        True when the hit was stored; False when the path was rejected.
    """
    normalized = normalize_path(path)
    if not normalized:
        return False

    user = getattr(request, "user", None)
    if (
        user is not None
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
    ):
        # Do not pollute Admin analytics with staff browsing the public SPA.
        return True

    inferred_type, inferred_key = classify_path(normalized)
    otype = object_type if object_type in ObjectType.values else inferred_type
    okey = (object_key or inferred_key or "")[:_MAX_KEY]
    clean_title = (title or "").strip()[:_MAX_TITLE]

    visitor_id = ensure_visitor_id(request)
    if not visitor_id:
        return False

    day = timezone.localdate()
    path_unique = _mark_unique("path", day, visitor_id, normalized)
    site_unique = _mark_unique("site", day, visitor_id)

    _bump_page_stat(
        day=day,
        path=normalized,
        object_type=otype,
        object_key=okey,
        title=clean_title,
        path_unique=path_unique,
    )
    _bump_site_stat(day=day, site_unique=site_unique)
    return True


def _bump_page_stat(
    *,
    day: date,
    path: str,
    object_type: str,
    object_key: str,
    title: str,
    path_unique: bool,
) -> None:
    """Increment or create :class:`PageDailyStat` for the path."""
    updates: dict[str, Any] = {"views": F("views") + 1}
    if path_unique:
        updates["unique_visitors"] = F("unique_visitors") + 1
    if title:
        updates["title"] = title

    with transaction.atomic():
        updated = PageDailyStat.objects.filter(day=day, path=path).update(**updates)
        if updated:
            return
        try:
            PageDailyStat.objects.create(
                day=day,
                path=path,
                object_type=object_type,
                object_key=object_key,
                title=title,
                views=1,
                unique_visitors=1 if path_unique else 0,
            )
        except IntegrityError:
            PageDailyStat.objects.filter(day=day, path=path).update(**updates)


def _bump_site_stat(*, day: date, site_unique: bool) -> None:
    """Increment or create :class:`SiteDailyStat` for the day."""
    updates: dict[str, Any] = {"views": F("views") + 1}
    if site_unique:
        updates["unique_visitors"] = F("unique_visitors") + 1

    with transaction.atomic():
        updated = SiteDailyStat.objects.filter(day=day).update(**updates)
        if updated:
            return
        try:
            SiteDailyStat.objects.create(
                day=day,
                views=1,
                unique_visitors=1 if site_unique else 0,
            )
        except IntegrityError:
            SiteDailyStat.objects.filter(day=day).update(**updates)


def build_site_analytics_stats(*, days: int = 30, limit: int = 20) -> dict[str, Any]:
    """Build Admin analytics payload for a period.

    Args:
        days: Lookback window (0 = all time).
        limit: Rows per top list.

    Returns:
        Totals, daily series, top pages, top SKUs.
    """
    since: date | None = None
    if days > 0:
        since = timezone.localdate() - timedelta(days=days - 1)

    site_qs = SiteDailyStat.objects.all()
    page_qs = PageDailyStat.objects.all()
    if since is not None:
        site_qs = site_qs.filter(day__gte=since)
        page_qs = page_qs.filter(day__gte=since)

    site_agg = site_qs.aggregate(
        views=Sum("views"),
        unique_visitors=Sum("unique_visitors"),
    )
    totals = {
        "views": int(site_agg["views"] or 0),
        "unique_visitors": int(site_agg["unique_visitors"] or 0),
        "days": days,
    }

    today = timezone.localdate()
    today_row = SiteDailyStat.objects.filter(day=today).first()
    today_stats = {
        "views": today_row.views if today_row else 0,
        "unique_visitors": today_row.unique_visitors if today_row else 0,
    }

    daily = [
        {
            "day": row.day,
            "views": row.views,
            "unique_visitors": row.unique_visitors,
        }
        for row in site_qs.order_by("day")
    ]

    top_pages = _top_paths(page_qs, limit=limit)
    top_skus = _top_paths(
        page_qs.filter(object_type=ObjectType.SKU),
        limit=limit,
    )
    top_content = _top_paths(
        page_qs.filter(
            object_type__in=(ObjectType.PAGE, ObjectType.ARTICLE, ObjectType.NEWS),
        ),
        limit=limit,
    )

    return {
        "totals": totals,
        "today": today_stats,
        "daily": daily,
        "top_pages": top_pages,
        "top_skus": top_skus,
        "top_content": top_content,
    }


def _top_paths(qs: Any, *, limit: int) -> list[dict[str, Any]]:
    """Aggregate views by path over the filtered queryset."""
    rows = (
        qs.values("path", "object_type", "object_key")
        .annotate(
            views=Sum("views"),
            unique_visitors=Sum("unique_visitors"),
        )
        .order_by("-views")[:limit]
    )
    # Latest non-empty title per path (best-effort).
    titles: dict[str, str] = {}
    for path in {row["path"] for row in rows}:
        titled = (
            PageDailyStat.objects.filter(path=path)
            .exclude(title="")
            .order_by("-day")
            .values_list("title", flat=True)
            .first()
        )
        if titled:
            titles[path] = titled

    out: list[dict[str, Any]] = []
    for row in rows:
        otype = row["object_type"]
        label = dict(ObjectType.choices).get(otype, otype)
        out.append(
            {
                "path": row["path"],
                "object_type": otype,
                "object_type_label": label,
                "object_key": row["object_key"],
                "title": titles.get(row["path"], ""),
                "views": int(row["views"] or 0),
                "unique_visitors": int(row["unique_visitors"] or 0),
            },
        )
    return out
