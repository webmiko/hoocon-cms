"""Load index.html and render SPA responses with server-side SEO head."""

from __future__ import annotations

import json
import re
import secrets
import threading
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

from config.seo.head import apply_seo_head, inject_json_ld, resolve_seo_context
from config.seo.json_ld import build_json_ld

# Keep in sync with ``frontend/.../HomePage.tsx`` hero (LCP / first paint).
HOME_LCP_IMAGE = "/home/projects/beijing-metro.webp"
HOME_SSR_BRAND = "HOOCON"
HOME_SSR_H1 = "Электроприводы для вентиляции и кондиционирования"
HOME_SSR_LEAD = (
    "Подбор за минуту на главной, каталог по параметрам, паспорта, аналоги Belimo. "
    "Склад в Москве — отгрузка по РФ. КП по запросу."
)

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


def _home_ssr_hero_css() -> str:
    """Critical CSS for the server-rendered home hero (no React, no entry CSS)."""
    # Fixed overlay outside ``#root`` so ``createRoot`` cannot wipe the LCP img.
    return """
#hoocon-ssr-hero{position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;
justify-content:flex-end;min-height:100vh;padding:72px 24px 48px;background:#101010;color:#fff;
overflow:hidden;box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
#hoocon-ssr-hero .hoocon-ssr-hero__img{position:absolute;inset:0;width:100%;height:100%;
object-fit:cover;pointer-events:none}
#hoocon-ssr-hero .hoocon-ssr-hero__shade{position:absolute;inset:0;pointer-events:none;background:
linear-gradient(105deg,rgba(12,12,12,.88) 0%,rgba(12,12,12,.55) 45%,rgba(12,12,12,.4) 100%),
linear-gradient(180deg,rgba(12,12,12,.25) 0%,transparent 40%,rgba(12,12,12,.5) 100%)}
#hoocon-ssr-hero .hoocon-ssr-hero__brand{position:relative;z-index:1;max-width:1120px;width:100%;
margin:0 auto}
#hoocon-ssr-hero .hoocon-ssr-hero__eyebrow{margin:0 0 12px;font-size:12px;font-weight:700;
letter-spacing:.18em;text-transform:uppercase;color:rgba(255,255,255,.72)}
#hoocon-ssr-hero .hoocon-ssr-hero__title{margin:0 0 16px;font-size:clamp(1.75rem,4vw + .5rem,2.75rem);
line-height:1.15;font-weight:700;max-width:18ch}
#hoocon-ssr-hero .hoocon-ssr-hero__lead{margin:0 0 28px;font-size:1.05rem;line-height:1.45;
max-width:36rem;color:rgba(255,255,255,.88)}
#hoocon-ssr-hero .hoocon-ssr-hero__actions{display:flex;flex-wrap:wrap;gap:12px}
#hoocon-ssr-hero .hoocon-ssr-hero__cta{display:inline-flex;align-items:center;justify-content:center;
min-height:44px;padding:0 20px;border-radius:8px;font-size:1rem;font-weight:600;text-decoration:none}
#hoocon-ssr-hero .hoocon-ssr-hero__cta--primary{background:#da0e2b;color:#fff}
#hoocon-ssr-hero .hoocon-ssr-hero__cta--secondary{background:transparent;color:#fff;
border:1px solid rgba(255,255,255,.55)}
""".replace("\n", "")


def _home_ssr_hero_markup() -> str:
    """Semantic home hero HTML painted before the SPA JS runs."""
    brand = escape(HOME_SSR_BRAND)
    title = escape(HOME_SSR_H1)
    lead = escape(HOME_SSR_LEAD)
    img = escape(HOME_LCP_IMAGE, quote=True)
    return (
        f'<section id="hoocon-ssr-hero" aria-labelledby="hoocon-ssr-brand">'
        f'<img class="hoocon-ssr-hero__img" id="hoocon-lcp-boot" src="{img}" alt="" '
        f'width="960" height="640" decoding="async" fetchpriority="high">'
        f'<div class="hoocon-ssr-hero__shade" aria-hidden="true"></div>'
        f'<div class="hoocon-ssr-hero__brand">'
        f'<p id="hoocon-ssr-brand" class="hoocon-ssr-hero__eyebrow">{brand}</p>'
        f'<h1 class="hoocon-ssr-hero__title">{title}</h1>'
        f'<p class="hoocon-ssr-hero__lead">{lead}</p>'
        f'<div class="hoocon-ssr-hero__actions">'
        f'<a class="hoocon-ssr-hero__cta hoocon-ssr-hero__cta--primary" href="/catalog">'
        f"Смотреть каталог</a>"
        f'<a class="hoocon-ssr-hero__cta hoocon-ssr-hero__cta--secondary" href="/#podbor">'
        f"Подобрать модель</a>"
        f'<a class="hoocon-ssr-hero__cta hoocon-ssr-hero__cta--secondary" href="/consultation">'
        f"Запросить КП</a>"
        f"</div></div></section>"
    )


def _home_ssr_podbor_noscript() -> str:
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


_ENTRY_MODULE_RE = re.compile(
    r'<script\b[^>]*\btype=["\']module["\'][^>]*\bsrc=["\']([^"\']+)["\'][^>]*>\s*</script>',
    re.IGNORECASE,
)
_MODULEPRELOAD_RE = re.compile(
    r'<link\b[^>]*\brel=["\']modulepreload["\'][^>]*>\s*',
    re.IGNORECASE,
)


def _defer_home_entry_until_lcp(html: str) -> str:
    """Start the SPA entry module only after the LCP boot image has loaded.

    On Slow 4G, ``modulepreload`` + large ``vendor-react`` contend with the hero
    WebP and block the main thread before the image can paint — LCP stays ~3–4s.
    Waiting for ``#hoocon-lcp-boot`` ``load`` (with a safety timeout) lets the
    SSR hero become LCP before JS download/parse.

    Args:
        html: Home HTML that already contains the SSR LCP boot image.

    Returns:
        HTML with modulepreloads removed and entry script deferred.
    """
    match = _ENTRY_MODULE_RE.search(html)
    if not match:
        return html

    src = match.group(1)
    src_js = json.dumps(src)
    html = _MODULEPRELOAD_RE.sub("", html)
    # Inline loader gets a CSP nonce via ``inject_csp_nonce`` (runs after this).
    loader = (
        '<script type="module">'
        "(function(){"
        f"var src={src_js};"
        "var started=false;"
        "function boot(){"
        "if(started)return;"
        "started=true;"
        'var s=document.createElement("script");'
        's.type="module";'
        's.crossOrigin="";'
        "s.src=src;"
        "document.head.appendChild(s);"
        "}"
        'var img=document.getElementById("hoocon-lcp-boot");'
        "if(img&&!img.complete){"
        'img.addEventListener("load",boot,{once:true});'
        'img.addEventListener("error",boot,{once:true});'
        "}else{boot();}"
        "setTimeout(boot,2500);"
        "})();"
        "</script>"
    )
    return _ENTRY_MODULE_RE.sub(loader, html, count=1)


def inject_home_lcp_hints(html: str, raw_path: str) -> str:
    """Server-render home hero (image + copy) before React mounts.

    Not full React SSR — a static shell for ``/`` so FCP/LCP can fire from
    HTML+critical CSS while ``vendor-react`` downloads. The shell is a
    **sibling before** ``#root`` so ``createRoot`` does not destroy the LCP
    ``<img>``; HomePage adopts that node into the React hero on mount.
    Entry JS is deferred until the boot image loads (mobile LCP).

    Args:
        html: SPA shell HTML.
        raw_path: Request path.

    Returns:
        HTML with home LCP preload + SSR hero, or unchanged for other routes.
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

    if 'id="hoocon-ssr-hero"' not in html:
        style = f'<style id="hoocon-ssr-hero-css">{_home_ssr_hero_css()}</style>'
        html = html.replace("</head>", f"    {style}\n  </head>", 1)
        boot = _home_ssr_hero_markup()
        # Outside ``#root``: LCP img survives createRoot; React adopts it.
        html = html.replace(
            '<div id="root"></div>',
            f'{boot}<div id="root"></div>{_home_ssr_podbor_noscript()}',
            1,
        )

    return _defer_home_entry_until_lcp(html)


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
    html = inject_home_lcp_hints(html, raw_path)
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
