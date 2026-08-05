/** Canonical nested catalog paths (SEO: one page per SKU). */

/**
 * Normalize one path fragment: trim slashes, drop leading ``catalog/``.
 */
function pathSegment(value: string): string {
  let segment = value.trim().replace(/^\/+|\/+$/g, "");
  while (true) {
    const lower = segment.toLowerCase();
    if (lower === "catalog") {
      return "";
    }
    if (lower.startsWith("catalog/")) {
      segment = segment.slice("catalog/".length).replace(/^\/+|\/+$/g, "");
      continue;
    }
    break;
  }
  return segment;
}

export function catalogCategoryPath(categorySlug: string): string {
  const slug = pathSegment(categorySlug);
  return slug ? `/catalog/${slug}` : "/catalog";
}

export function catalogSkuPath(categorySlug: string, skuSlug: string): string {
  const cat = pathSegment(categorySlug);
  let sku = pathSegment(skuSlug);
  if (!cat || !sku) return "/catalog";
  // ``sku`` may already be ``{cat}/{sku}`` (or repeated cat prefixes).
  let parts = sku.split("/").filter(Boolean);
  while (parts.length >= 2 && parts[0]!.toLowerCase() === cat.toLowerCase()) {
    parts = parts.slice(1);
  }
  sku = parts.join("/");
  if (!sku) return catalogCategoryPath(cat);
  return `/catalog/${cat}/${sku}`;
}

/** Path for a list/detail SKU card. Falls back to /catalog if category missing. */
export function catalogPathForSku(sku: {
  category_slug?: string | null;
  slug?: string | null;
}): string {
  const cat = sku.category_slug ?? "";
  const slug = sku.slug ?? "";
  if (!cat || !slug) return "/catalog";
  return catalogSkuPath(cat, slug);
}
