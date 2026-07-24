"""JSON-LD whitelist builders for source HTML (БЗ M2, Z3/Z4)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from config.seo.head import SeoHeadContext
from config.seo.routes import DEFAULT_DESCRIPTION, HOME_FAQ_ITEMS, SITE_NAME


def build_json_ld(context: SeoHeadContext) -> list[dict[str, Any]]:
    """Build schema.org blocks for a pathname (whitelist fields only).

    Args:
        context: Resolved SEO context.

    Returns:
        List of JSON-LD objects for injection into HTML.
    """
    site_url = settings.SITE_URL.rstrip("/")
    blocks: list[dict[str, Any]] = []

    if context.canonical_path == "/":
        blocks.append(_organization(site_url))
        blocks.append(_website(site_url))
        blocks.append(_faq_page(site_url, HOME_FAQ_ITEMS))
        return blocks

    if context.canonical_path == "/faq":
        blocks.append(_faq_page(site_url, HOME_FAQ_ITEMS))
        blocks.extend(_breadcrumb(site_url, context))
        return blocks

    if context.canonical_path == "/kontakty":
        blocks.append(_organization(site_url))
        blocks.extend(_breadcrumb(site_url, context))
        return blocks

    if context.sku_code and context.og_type == "product":
        blocks.append(_product(site_url, context))
        blocks.extend(_breadcrumb(site_url, context))
        return blocks

    if context.og_type == "article" and context.article_published_at:
        blocks.append(_article(site_url, context))
        blocks.extend(_breadcrumb(site_url, context))
        return blocks

    blocks.extend(_breadcrumb(site_url, context))
    return blocks


def _organization(site_url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": site_url,
        "description": DEFAULT_DESCRIPTION,
    }


def _website(site_url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": site_url,
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{site_url}/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def _faq_page(site_url: str, items: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "url": f"{site_url}/faq" if items else site_url,
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in items
        ],
    }


def _article(site_url: str, context: SeoHeadContext) -> dict[str, Any]:
    headline = context.page_title.split(" — ")[0]
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": headline,
        "description": context.description,
        "url": f"{site_url}{context.canonical_path}",
        "datePublished": context.article_published_at,
        "author": {"@type": "Organization", "name": SITE_NAME, "url": site_url},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": site_url},
    }


def _product(site_url: str, context: SeoHeadContext) -> dict[str, Any]:
    name = context.page_title.split(" — ")[0]
    # Storefront: zero stock = made-to-order (never «out of stock» UX).
    availability = "https://schema.org/InStock" if context.in_stock else "https://schema.org/PreOrder"
    offer: dict[str, Any] = {
        "@type": "Offer",
        "availability": availability,
    }
    if context.sku_price and not context.price_on_request:
        offer["price"] = context.sku_price
        offer["priceCurrency"] = "RUB"
    else:
        offer["priceSpecification"] = {
            "@type": "PriceSpecification",
            "priceCurrency": "RUB",
        }
    product: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "sku": context.sku_code,
        "description": context.description,
        "url": f"{site_url}{context.canonical_path}",
        "offers": offer,
    }
    if context.category_name:
        product["category"] = context.category_name
    return product


def _breadcrumb(site_url: str, context: SeoHeadContext) -> list[dict[str, Any]]:
    if len(context.breadcrumb) < 2:
        return []
    elements = []
    for index, (path, name) in enumerate(context.breadcrumb, start=1):
        item_url = f"{site_url}{path}" if path.startswith("/") else path
        elements.append(
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": item_url,
            }
        )
    return [
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": elements,
        }
    ]
