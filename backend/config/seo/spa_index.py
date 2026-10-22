"""Load index.html and render SPA responses with server-side SEO head."""

from __future__ import annotations

import re
import secrets
import threading
from dataclasses import replace
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponsePermanentRedirect

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


def inject_home_lcp_hints(html: str, raw_path: str) -> str:
    """Preload home hero LCP image.

    The picker text lives in the crawl block inside #root. React replaces
    #root; there is no second noscript copy and no SSR overlay.

    Args:
        html: SPA shell HTML.
        raw_path: Request path.

    Returns:
        HTML with home LCP preload, or unchanged for other routes.
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

    return html


def inject_crawl_block(
    html: str,
    heading: str,
    lines: tuple[str, ...],
    links: tuple[tuple[str, str], ...] = (),
) -> str:
    """Put the heading, facts and links inside #root before the script runs.

    React replaces #root on startup, so visitors do not keep a second copy.
    Crawlers that do not run scripts still see the title, the text and the
    links. The block is not ``hidden``: a hidden article is skipped.

    Args:
        html: SPA shell.
        heading: Page h1.
        lines: Short fact lines.
        links: ``(href, label)`` pairs.

    Returns:
        HTML with the crawl block, or unchanged when there is nothing to say.
    """
    if 'id="seo-crawl"' in html:
        return html
    if not heading and not lines and not links:
        return html
    parts: list[str] = []
    if heading:
        parts.append(f"<h1>{escape(heading)}</h1>")
    if lines:
        items = "".join(f"<li>{escape(line)}</li>" for line in lines)
        parts.append(f"<ul>{items}</ul>")
    if links:
        anchors = "".join(
            f'<a href="{escape(href, quote=True)}">{escape(label)}</a>' for href, label in links if href and label
        )
        if anchors:
            parts.append(f"<nav>{anchors}</nav>")
    if not parts:
        return html
    block = f'<article id="seo-crawl">{"".join(parts)}</article>'
    return html.replace('<div id="root"></div>', f'<div id="root">{block}</div>', 1)


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
    if context.http_status == 301 and context.redirect_to:
        target = context.redirect_to
        if target.startswith("/"):
            target = f"{settings.SITE_URL.rstrip('/')}{target}"
        return HttpResponsePermanentRedirect(target)
    if _catalog_query_is_a_filter(raw_path, query_string):
        context = replace(context, noindex=True)
    site_url = settings.SITE_URL.rstrip("/")
    canonical_url = f"{site_url}{context.canonical_path}"

    html = load_index_html()
    html = apply_seo_head(html, context, canonical_url=canonical_url)
    html = inject_json_ld(html, build_json_ld(context), nonce=nonce)
    html = inject_crawl_block(
        html,
        context.crawl_heading,
        context.crawl_lines,
        context.crawl_links,
    )
    html = inject_home_lcp_hints(html, raw_path)
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
