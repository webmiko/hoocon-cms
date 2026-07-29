import { Helmet } from "react-helmet-async";

import { canonicalizePath } from "../utils/canonicalizePath";
import {
  absoluteOgImageUrl,
  brandedTitle,
  SITE_URL,
} from "../utils/seoMeta";

const SITE_NAME = "Hoocon";
const DEFAULT_OG_IMAGE = `${SITE_URL}/og-image.svg`;

interface SeoProps {
  title: string;
  description?: string;
  /** Canonical path (e.g. "/catalog"). Full URL is derived from SITE_URL. */
  path?: string;
  /** Optional JSON-LD object (already whitelisted by the caller). */
  jsonLd?: Record<string, unknown> | Record<string, unknown>[];
  /** OpenGraph type: website | article | product. */
  ogType?: "website" | "article" | "product";
  /** When true, emit robots noindex,nofollow. */
  noindex?: boolean;
  /** Optional image URL to ``<link rel="preload" as="image">`` (LCP). */
  preloadImage?: string;
  /**
   * Absolute or site-relative image for og:image / twitter:image.
   * Falls back to site-wide ``/og-image.svg``.
   */
  image?: string | null;
}

function cspNonce(): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }
  return (
    document.querySelector('meta[name="csp-nonce"]')?.getAttribute("content") ??
    undefined
  );
}

/**
 * SEO head: title, description, canonical, OG, Twitter, optional JSON-LD.
 *
 * Spec: ПЛАН §6 Iter 4 — F9; БЗ SEO-индексация-SPA.md (no trailing slash).
 */
export function Seo({
  title,
  description,
  path,
  jsonLd,
  ogType = "website",
  noindex = false,
  preloadImage,
  image,
}: SeoProps) {
  const fullTitle = brandedTitle(title);
  const canonicalPath = path ? canonicalizePath(path) : "/";
  const canonical =
    canonicalPath === "/" ? SITE_URL : `${SITE_URL}${canonicalPath}`;
  const robots = noindex ? "noindex, nofollow" : "index, follow";
  const ogImage = absoluteOgImageUrl(image) ?? DEFAULT_OG_IMAGE;
  const nonce = cspNonce();
  const blocks = jsonLd
    ? Array.isArray(jsonLd)
      ? jsonLd
      : [jsonLd]
    : [];

  return (
    <Helmet>
      <title>{fullTitle}</title>
      {description && <meta name="description" content={description} />}
      <meta name="robots" content={robots} />
      <link rel="canonical" href={canonical} />
      {preloadImage ? (
        <link
          rel="preload"
          as="image"
          href={preloadImage}
          fetchPriority="high"
        />
      ) : null}

      <meta property="og:site_name" content={SITE_NAME} />
      <meta property="og:title" content={fullTitle} />
      {description && <meta property="og:description" content={description} />}
      <meta property="og:type" content={ogType} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={ogImage} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      {description && <meta name="twitter:description" content={description} />}
      <meta name="twitter:image" content={ogImage} />

      {!noindex && (
        <>
          <link rel="alternate" hrefLang="ru" href={canonical} />
          <link rel="alternate" hrefLang="x-default" href={canonical} />
        </>
      )}

      {blocks.map((block, index) => (
        <script
          key={index}
          type="application/ld+json"
          nonce={nonce}
        >
          {JSON.stringify(block)}
        </script>
      ))}
    </Helmet>
  );
}
