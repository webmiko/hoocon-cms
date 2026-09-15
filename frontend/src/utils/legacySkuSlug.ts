/**
 * Guard legacy ``/:slug`` SKU redirects — skip API when the path cannot be a catalog SKU.
 */

const LEGACY_SKU_SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)+$/;

/** Known app paths that must not hit ``/api/catalog/skus/{slug}/`` before 404. */
const RESERVED_LEGACY_SLUGS = new Set([
  "admin",
  "api",
  "assets",
  "media",
  "static",
  "sw.js",
  "manifest.webmanifest",
  "robots.txt",
  "sitemap.xml",
]);

/**
 * Whether ``/:slug`` should call the SKU detail API (legacy flat URLs).
 *
 * SKU slugs are lowercase hyphenated paths (e.g. ``privod-vozdushniy-hva-5nm-s``).
 * Short or single-token paths like ``about`` skip the network round-trip.
 */
export function shouldResolveLegacySkuSlug(slug: string): boolean {
  const normalized = slug.trim().toLowerCase();
  if (normalized.length < 8 || RESERVED_LEGACY_SLUGS.has(normalized)) {
    return false;
  }
  return LEGACY_SKU_SLUG_RE.test(normalized);
}
