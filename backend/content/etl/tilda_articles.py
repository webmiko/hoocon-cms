"""Fetch and normalize Tilda blog posts from hoocon.ru/statyi feed.

Source feed: https://feeds.tildacdn.com/api/getfeed/?feeduid=…
Full post: https://feeds.tildacdn.com/api/getpost/?postuid=…
"""

from __future__ import annotations

import html
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_FEED_UID = "914359848731"
NEWS_FEED_UID = "804480635191"
FEED_API = "https://feeds.tildacdn.com/api/getfeed/"
POST_API = "https://feeds.tildacdn.com/api/getpost/"
_USER_AGENT = "HooconCMS/1.0 (+https://hoocon.ru; articles-import)"
_MOSCOW = ZoneInfo("Europe/Moscow")
_TAG_RE = re.compile(r"<[^>]+>")
_IMG_SRC_RE = re.compile(
    r'(?P<prefix><img\b[^>]*?\bsrc=["\'])(?P<url>[^"\']+)(?P<suffix>["\'])',
    re.I,
)
_STATIC_URL_RE = re.compile(
    r"https?://(?:static\.tildacdn\.com|thb\.tildacdn\.com)/[^\s\"'<>]+",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ScrapedArticle:
    """Normalized article ready for ORM load."""

    uid: str
    slug: str
    title: str
    excerpt: str
    body_html: str
    cover_url: str
    published_at: datetime | None
    source_url: str


def _http_get_json(url: str, *, timeout: float = 30.0) -> dict[str, object]:
    """GET JSON from Tilda feeds API."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = resp.read()
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON root type: {type(data)}")
    return data


def fetch_feed_posts(feed_uid: str = DEFAULT_FEED_UID) -> list[dict[str, object]]:
    """Return post stubs from the Tilda feed (title, url, uid, cover)."""
    url = f"{FEED_API}?feeduid={feed_uid}"
    data = _http_get_json(url)
    posts = data.get("posts")
    if not isinstance(posts, list):
        return []
    return [p for p in posts if isinstance(p, dict)]


def fetch_post(post_uid: str) -> dict[str, object]:
    """Return the full Tilda post payload (includes HTML ``text``)."""
    url = f"{POST_API}?postuid={post_uid}"
    data = _http_get_json(url)
    post = data.get("post")
    if not isinstance(post, dict):
        raise ValueError(f"Missing post for uid={post_uid}")
    return post


def slug_from_tilda_url(url: str) -> str:
    """Extract canonical slug from Tilda article/news URL.

    ``/statyi/tpost/<slug>`` → ``<slug>``.
    ``/news/partner/foo`` → ``partner-foo`` (no slash; SlugField-safe).
    """
    path = (url or "").rstrip("/")
    if "/tpost/" in path:
        return path.rsplit("/tpost/", 1)[-1].strip("/").replace("/", "-")
    if "/news/" in path:
        return path.split("/news/", 1)[-1].strip("/").replace("/", "-")
    if "/novosti/" in path:
        return path.split("/novosti/", 1)[-1].strip("/").replace("/", "-")
    return path.rsplit("/", 1)[-1].strip("/").replace("/", "-")


def strip_html_to_text(raw: str) -> str:
    """Remove tags and unescape entities for excerpt/plain text."""
    text = _TAG_RE.sub(" ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_article_html(raw: str) -> str:
    """Light cleanup of Tilda redactor HTML for CMS body.

    Keeps tables/links; drops empty wrapper noise; does not rewrite images
    (caller downloads and rewrites URLs separately).
    """
    body = (raw or "").strip()
    body = re.sub(
        r'^<div class="t-redactor__tte-view">\s*',
        "",
        body,
        count=1,
        flags=re.I,
    )
    if body.endswith("</div>"):
        # Only strip outermost closing div when we removed the opener.
        body = re.sub(r"</div>\s*$", "", body, count=1, flags=re.I)
    body = re.sub(r'\sclass="t-redactor__[a-z0-9\-]+"', "", body, flags=re.I)
    body = re.sub(r"<div id=\"[^\"]*\" class=\"t-redactor__anchor\"></div>", "", body)
    return body.strip()


def parse_published_at(value: str, *, tz: ZoneInfo = _MOSCOW) -> datetime | None:
    """Parse Tilda ``published`` / ``date`` into aware datetime."""
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(raw, fmt)
            return naive.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def collect_image_urls(html_body: str, *extra: str) -> list[str]:
    """Unique absolute image URLs from HTML plus optional cover URLs."""
    found: list[str] = []
    seen: set[str] = set()
    for url in extra:
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    for match in _STATIC_URL_RE.finditer(html_body or ""):
        url = match.group(0)
        if url not in seen:
            seen.add(url)
            found.append(url)
    for match in _IMG_SRC_RE.finditer(html_body or ""):
        url = match.group("url")
        if url.startswith("http") and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def rewrite_image_urls(html_body: str, mapping: dict[str, str]) -> str:
    """Replace remote image URLs with local media paths."""
    if not mapping:
        return html_body

    def _sub(match: re.Match[str]) -> str:
        url = match.group("url")
        local = mapping.get(url, url)
        return f"{match.group('prefix')}{local}{match.group('suffix')}"

    out = _IMG_SRC_RE.sub(_sub, html_body)
    for remote, local in mapping.items():
        out = out.replace(remote, local)
    return out


def download_bytes(url: str, *, timeout: float = 60.0) -> bytes:
    """Download raw bytes from an absolute URL."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def scrape_article(post_stub: dict[str, object]) -> ScrapedArticle:
    """Build a ScrapedArticle from a feed stub + full getpost payload."""
    uid = str(post_stub.get("uid") or "").strip()
    if not uid:
        raise ValueError("post stub missing uid")
    full = fetch_post(uid)
    source_url = str(full.get("url") or post_stub.get("url") or "")
    slug = slug_from_tilda_url(source_url)
    if not slug:
        raise ValueError(f"cannot derive slug for uid={uid}")
    title = str(full.get("title") or post_stub.get("title") or "").strip()
    descr = str(full.get("descr") or post_stub.get("descr") or "")
    body = clean_article_html(str(full.get("text") or ""))
    cover = str(
        full.get("image") or post_stub.get("image") or full.get("thumb") or post_stub.get("thumb") or "",
    ).strip()
    published = parse_published_at(
        str(full.get("published") or full.get("date") or ""),
    )
    return ScrapedArticle(
        uid=uid,
        slug=slug[:300],
        title=title[:300] or slug,
        excerpt=strip_html_to_text(descr)[:2000],
        body_html=body,
        cover_url=cover,
        published_at=published,
        source_url=source_url,
    )


def scrape_all_articles(feed_uid: str = DEFAULT_FEED_UID) -> list[ScrapedArticle]:
    """Scrape every post from the feed (newest first as returned by Tilda)."""
    stubs = fetch_feed_posts(feed_uid)
    articles: list[ScrapedArticle] = []
    for stub in stubs:
        try:
            articles.append(scrape_article(stub))
        except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("skip post %s: %s", stub.get("uid"), exc)
    return articles
