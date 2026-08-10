/**
 * Canonical SPA path without trailing slash (БЗ SEO-индексация-SPA.md).
 */

/**
 * Normalize a path for canonical URLs (no trailing slash except `/`).
 *
 * Query/hash are stripped — filter state is not part of the canonical URL.
 */
export function canonicalizePath(path: string): string {
  const bare = path.split("?")[0]?.split("#")[0] ?? "/";
  if (!bare || bare === "/") {
    return "/";
  }
  const withSlash = bare.startsWith("/") ? bare : `/${bare}`;
  return withSlash.replace(/\/+$/, "") || "/";
}
