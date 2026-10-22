"""Load index.html and render SPA responses with server-side SEO head."""

from __future__ import annotations

import re
import secrets
import threading
from dataclasses import replace
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

from config.seo.head import apply_seo_head, inject_json_ld, resolve_seo_context
from config.seo.json_ld import build_json_ld

# Keep in sync with ``frontend/.../HomePage.tsx`` hero (LCP preload).
HOME_LCP_IMAGE = "/home/projects/beijing-metro.webp"

_index_cache_lock = threading.Lock()
_index_cache: tuple[int, str] | None = None


def _index_html_path() -> Path:
    return Path(settings.SPA_INDEX_HTML)


def load_index_html() -> str:
    """Read index.html with mtime cache.

    Returns:
        HTML string of the SPA shell.

    Raises:
        Http404: File missing.
    """
    global _index_cache
    path = _index_html_path()
    if not path.is_file():
        raise Http404
    mtime_ns = path.stat().st_mtime_ns
    with _index_cache_lock:
        if _index_cache is not None and _index_cache[0] == mtime_ns:
            return _index_cache[1]
        content = path.read_text(encoding="utf-8")
        _index_cache = (mtime_ns, content)
        return content


def clear_index_html_cache() -> None:
    """Reset index.html cache (tests)."""
    global _index_cache
    with _index_cache_lock:
        _index_cache = None


def inject_csp_nonce(html: str, nonce: str) -> str:
    """Add nonce= to script/style opening tags and expose meta csp-nonce.

    Args:
        html: HTML document.
        nonce: CSP nonce value.

    Returns:
        HTML with nonce attributes.
    """
    safe = escape(nonce, quote=True)

    def _script(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "nonce=" in tag.lower():
            return tag
        return tag[:-1] + f' nonce="{safe}">'

    def _style(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "nonce=" in tag.lower():
            return tag
        return tag[:-1] + f' nonce="{safe}">'

    html = re.sub(r"<script\b[^>]*>", _script, html, flags=re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>", _style, html, flags=re.IGNORECASE)
    meta = f'<meta name="csp-nonce" content="{safe}" />'
    if 'name="csp-nonce"' not in html.lower():
        html = html.replace("</head>", f"    {meta}\n  </head>", 1)
    return html


def _home_podbor_noscript() -> str:
    """Crawler/no-JS fallback for the home product picker (React mounts inside #root)."""
    heading = escape("Подбор модели за минуту")
    body = escape(
        "Укажите тип продукции и параметры из проекта: привод на заслонку, "
        "шаровой кран, комплект кран+привод или кронштейн BR-M/BR-ML под привод Hoocon. "
        "Сервис покажет подходящие позиции в каталоге.",
    )
    return (
        f'<noscript><section id="podbor-noscript" aria-labelledby="podbor-noscript-h">'
        f'<h2 id="podbor-noscript-h">{heading}</h2>'
        f"<p>{body}</p>"
        f'<p><a href="/catalog">Каталог электроприводов</a></p>'
        f"</section></noscript>"
    )


def inject_home_lcp_hints(html: str, raw_path: str) -> str:
    """Preload home hero LCP image and inject noscript podbor fallback.

    React paints the hero after entry JS — no SSR overlay (UX over lab LCP tricks).

    Args:
        html: SPA shell HTML.
        raw_path: Request path.

    Returns:
        HTML with home LCP preload + noscript, or unchanged for other routes.
    """
    path = (raw_path or "/").split("?", 1)[0]
    if path not in ("/", ""):
        return html

    preload_marker = f'rel="preload" as="image" href="{HOME_LCP_IMAGE}"'
    if preload_marker not in html:
        preload = f'<link rel="preload" as="image" href="{HOME_LCP_IMAGE}" fetchpriority="high" type="image/webp">'
        script_marker = '<script type="module"'
        lower = html.lower()
        idx = lower.find(script_marker)
        if idx != -1:
            html = html[:idx] + f"    {preload}\n    " + html[idx:]
        else:
            html = html.replace("</head>", f"    {preload}\n  </head>", 1)

    if 'id="podbor-noscript"' not in html:
        html = html.replace(
            '<div id="root"></div>',
            f'<div id="root"></div>{_home_podbor_noscript()}',
            1,
        )

    return html


def inject_sku_crawl_block(html: str, heading: str, lines: tuple[str, ...]) -> str:
    """Put the product heading and specs in the first HTML, before the script runs.

    The block is hidden so the React page does not show a second heading.
    The same facts are on the card after the script loads.

    Args:
        html: SPA shell.
        heading: Product name for the h1.
        lines: Short spec lines, including the article code.

    Returns:
        HTML with the crawl block, or unchanged when there is nothing to say.
    """
    if not heading or 'id="sku-crawl"' in html:
        return html
    items = "".join(f"<li>{escape(line)}</li>" for line in lines)
    spec = f"<ul>{items}</ul>" if items else ""
    block = f'<article id="sku-crawl" hidden><h1>{escape(heading)}</h1>{spec}</article>'
    return html.replace('<div id="root"></div>', f'<div id="root"></div>{block}', 1)


def render_spa_index_html(
    raw_path: str,
    *,
    nonce: str | None = None,
    query_string: str = "",
) -> HttpResponse:
    """Build SPA HTML for a route with SEO head and JSON-LD.

    Args:
        raw_path: Request path.
        nonce: Optional CSP nonce.

    Returns:
        HttpResponse with text/html body.
    """
    context = resolve_seo_context(raw_path)
    if _catalog_query_is_a_filter(raw_path, query_string):
        context = replace(context, noindex=True)
    site_url = settings.SITE_URL.rstrip("/")
    canonical_url = f"{site_url}{context.canonical_path}"

    html = load_index_html()
    html = apply_seo_head(html, context, canonical_url=canonical_url)
    html = inject_json_ld(html, build_json_ld(context), nonce=nonce)
    html = inject_home_lcp_hints(html, raw_path)
    html = inject_sku_crawl_block(html, context.crawl_heading, context.crawl_lines)
    if nonce:
        html = inject_csp_nonce(html, nonce)

    response = HttpResponse(
        html,
        content_type="text/html; charset=utf-8",
        status=context.http_status,
    )
    response["Cache-Control"] = "no-cache, must-revalidate"
    return response


def spa_index_view(request: HttpRequest) -> HttpResponse:
    """Catch-all view: serve SPA shell with per-route SEO head.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response for the SPA.
    """
    nonce = getattr(request, "csp_nonce", None) or secrets.token_urlsafe(16)
    request.csp_nonce = nonce  # type: ignore[attr-defined]
    return render_spa_index_html(
        request.path,
        nonce=nonce,
        query_string=request.META.get("QUERY_STRING", ""),
    )


def _catalog_query_is_a_filter(raw_path: str, query_string: str) -> bool:
    """A catalog listing with parameters is a filter, not its own page."""
    if not (query_string or "").strip():
        return False
    path = (raw_path or "/").split("?", 1)[0].rstrip("/") or "/"
    if path == "/catalog":
        return True
    if not path.startswith("/catalog/"):
        return False
    parts = [part for part in path.removeprefix("/catalog/").split("/") if part]
    return len(parts) == 1
