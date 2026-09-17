/**
 * JSON-LD builders with strict whitelists.
 *
 * Spec: ПЛАН §6 Iter 4 — F9; БЗ SEO-индексация-SPA.md; security-baseline §3.
 */

import { catalogPathForSku } from "./catalogPaths";

const SITE_NAME = "Hoocon";
const SITE_URL = "https://hoocon.ru";

interface SkuForJsonLd {
  name: string;
  slug: string;
  sku_code?: string;
  description?: string;
  price?: string | number | null;
  price_on_request?: boolean;
  in_stock?: boolean;
  category_name?: string;
  category_slug?: string | null;
}

interface ArticleForJsonLd {
  title: string;
  slug: string;
  description: string;
  published_at?: string | null;
  pathPrefix?: "/statyi" | "/novosti";
}

interface BreadcrumbItem {
  name: string;
  path: string;
}

export type FaqJsonLdItem = { question: string; answer: string };

/**
 * Build a JSON-LD Product object from a SKU with a strict whitelist.
 */
export function buildProductJsonLd(sku: SkuForJsonLd): Record<string, unknown> {
  const path =
    sku.category_slug && sku.slug
      ? catalogPathForSku({
          category_slug: sku.category_slug,
          slug: sku.slug,
        })
      : `/${sku.slug}`;
  const ld: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: sku.name,
    sku: sku.sku_code ?? sku.slug,
    url: `${SITE_URL}${path}`,
  };

  if (sku.description) {
    ld.description = sku.description;
  }
  if (sku.category_name) {
    ld.category = sku.category_name;
  }

  if (sku.price != null && !sku.price_on_request) {
    ld.offers = {
      "@type": "Offer",
      price: String(sku.price),
      priceCurrency: "RUB",
      availability:
        sku.in_stock === false
          ? "https://schema.org/PreOrder"
          : "https://schema.org/InStock",
    };
  } else {
    ld.offers = {
      "@type": "Offer",
      availability:
        sku.in_stock === false
          ? "https://schema.org/PreOrder"
          : "https://schema.org/InStock",
      priceSpecification: {
        "@type": "PriceSpecification",
        priceCurrency: "RUB",
      },
    };
  }

  return ld;
}

/** Organization + WebSite (+ SearchAction) for the home page. */
export function buildHomeJsonLd(
  faqItems: FaqJsonLdItem[] = [],
): Record<string, unknown>[] {
  const blocks: Record<string, unknown>[] = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
    },
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: SITE_NAME,
      url: SITE_URL,
      potentialAction: {
        "@type": "SearchAction",
        target: {
          "@type": "EntryPoint",
          urlTemplate: `${SITE_URL}/search?q={search_term_string}`,
        },
        "query-input": "required name=search_term_string",
      },
    },
  ];
  if (faqItems.length) {
    blocks.push(buildFaqJsonLd(faqItems));
  }
  return blocks;
}

/** FAQPage schema from Admin FAQ items. */
export function buildFaqJsonLd(
  items: FaqJsonLdItem[],
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}

/** Article / BlogPosting for /statyi and /novosti. */
export function buildArticleJsonLd(
  article: ArticleForJsonLd,
): Record<string, unknown> {
  const prefix = article.pathPrefix ?? "/statyi";
  const ld: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.description,
    url: `${SITE_URL}${prefix}/${article.slug}`,
    author: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
    publisher: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  };
  if (article.published_at) {
    ld.datePublished = article.published_at;
  }
  return ld;
}

/** BreadcrumbList from path segments. */
export function buildBreadcrumbJsonLd(
  items: BreadcrumbItem[],
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.path.startsWith("http")
        ? item.path
        : `${SITE_URL}${item.path === "/" ? "" : item.path}`,
    })),
  };
}
