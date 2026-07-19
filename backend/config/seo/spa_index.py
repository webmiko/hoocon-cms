"""Load index.html and render SPA responses with server-side SEO head."""

from __future__ import annotations

import re
import secrets
import threading
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

from config.seo.head import apply_seo_head, inject_json_ld, resolve_seo_context
from config.seo.json_ld import build_json_ld

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


def render_spa_index_html(raw_path: str, *, nonce: str | None = None) -> HttpResponse:
    """Build SPA HTML for a route with SEO head and JSON-LD.

    Args:
        raw_path: Request path.
        nonce: Optional CSP nonce.

    Returns:
        HttpResponse with text/html body.
    """
    context = resolve_seo_context(raw_path)
    site_url = settings.SITE_URL.rstrip("/")
    canonical_url = f"{site_url}{context.canonical_path}"

    html = load_index_html()
    html = apply_seo_head(html, context, canonical_url=canonical_url)
    html = inject_json_ld(html, build_json_ld(context), nonce=nonce)
    if nonce:
        html = inject_csp_nonce(html, nonce)

    response = HttpResponse(html, content_type="text/html; charset=utf-8")
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
    return render_spa_index_html(request.path, nonce=nonce)
